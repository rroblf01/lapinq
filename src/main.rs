use clap::Parser;
use log::{error, info, warn};
use serde::{Deserialize, Serialize};
use std::process::Stdio;
use std::sync::Arc;
use tokio::process::Command;
use tokio::sync::Semaphore;
use tokio_postgres::{connect, NoTls};
use uuid::Uuid;

#[derive(Parser, Debug)]
#[command(name = "lagomorph-worker", version)]
struct Args {
    #[arg(long, env = "DATABASE_URL", default_value = "postgresql://localhost:5432/lagomorph")]
    database_url: String,

    #[arg(long, default_value = "4")]
    concurrency: usize,

    #[arg(long, default_value = "0.1")]
    poll_interval_secs: f64,

    #[arg(long, default_value = "300")]
    task_timeout_secs: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct Task {
    id: Uuid,
    queue_name: String,
    task_name: String,
    module_path: String,
    args: serde_json::Value,
    kwargs: serde_json::Value,
    status: String,
    attempts: i32,
    max_retries: i32,
}

#[tokio::main]
async fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    let args = Args::parse();
    let worker_id = Uuid::new_v4().to_string();

    info!(
        "Worker {} starting (concurrency={}, poll_interval={}s, timeout={}s)",
        worker_id, args.concurrency, args.poll_interval_secs, args.task_timeout_secs
    );

    let (client, connection) = connect(&args.database_url, NoTls)
        .await
        .expect("Failed to connect to PostgreSQL");
    tokio::spawn(async move {
        if let Err(e) = connection.await {
            error!("PostgreSQL connection error: {}", e);
        }
    });

    // Ensure schema exists
    client
        .batch_execute(
            "
        CREATE TABLE IF NOT EXISTS lagomorph_tasks (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            queue_name   TEXT NOT NULL,
            task_name    TEXT NOT NULL,
            module_path  TEXT NOT NULL,
            args         JSONB NOT NULL DEFAULT '[]',
            kwargs       JSONB NOT NULL DEFAULT '{}',
            status       TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','completed','failed')),
            result       TEXT,
            error        TEXT,
            attempts     INT NOT NULL DEFAULT 0,
            max_retries  INT NOT NULL DEFAULT 3,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at   TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            worker_id    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status
            ON lagomorph_tasks(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
            ON lagomorph_tasks(scheduled_at)
            WHERE status = 'pending';
        ",
        )
        .await
        .expect("Failed to create schema");

    let semaphore = Arc::new(Semaphore::new(args.concurrency));
    let client = Arc::new(client);

    loop {
        let task = match claim_task(&client, &worker_id).await {
            Ok(Some(t)) => t,
            Ok(None) => {
                tokio::time::sleep(tokio::time::Duration::from_secs_f64(
                    args.poll_interval_secs,
                ))
                .await;
                continue;
            }
            Err(e) => {
                error!("Error claiming task: {}", e);
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                continue;
            }
        };

        let sem = semaphore.clone();
        let cl = client.clone();
        let timeout = args.task_timeout_secs;

        tokio::spawn(async move {
            let _permit = sem.acquire().await.unwrap();
            info!("Executing task {}", task.id);
            if let Err(e) = execute_task(&cl, &task, timeout).await {
                warn!("Task {} failed: {}", task.id, e);
            }
        });
    }
}

async fn claim_task(client: &tokio_postgres::Client, worker_id: &str) -> Result<Option<Task>, tokio_postgres::Error> {
    let row = client
        .query_opt(
            "
            UPDATE lagomorph_tasks
            SET status = 'running',
                started_at = now(),
                worker_id = $1
            WHERE id = (
                SELECT id FROM lagomorph_tasks
                WHERE status = 'pending'
                AND scheduled_at <= now()
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, queue_name, task_name, module_path, args, kwargs, status, attempts, max_retries
            ",
            &[&worker_id],
        )
        .await?;

    match row {
        Some(r) => Ok(Some(Task {
            id: r.get(0),
            queue_name: r.get(1),
            task_name: r.get(2),
            module_path: r.get(3),
            args: r.get(4),
            kwargs: r.get(5),
            status: r.get(6),
            attempts: r.get(7),
            max_retries: r.get(8),
        })),
        None => Ok(None),
    }
}

async fn execute_task(
    client: &tokio_postgres::Client,
    task: &Task,
    timeout_secs: u64,
) -> Result<(), String> {
    let result = tokio::time::timeout(
        tokio::time::Duration::from_secs(timeout_secs),
        run_python_subprocess(task),
    )
    .await;

    match result {
        Ok(Ok((stdout, _))) => {
            info!("Task {} completed successfully", task.id);
            complete_task_in_db(client, task.id, &stdout)
                .await
                .map_err(|e| e.to_string())?;
            Ok(())
        }
        Ok(Err((stderr, attempts, max_retries))) => {
            let msg = if stderr.is_empty() {
                "unknown error".to_string()
            } else {
                stderr.clone()
            };
            warn!("Task {} failed: {}", task.id, msg);
            fail_task_in_db(client, task.id, &msg, attempts, max_retries)
                .await
                .map_err(|e| e.to_string())?;
            Ok(())
        }
        Err(_) => {
            warn!("Task {} timed out after {}s", task.id, timeout_secs);
            fail_task_in_db(client, task.id, "timed out", 0, 3)
                .await
                .map_err(|e| e.to_string())?;
            Ok(())
        }
    }
}

async fn run_python_subprocess(task: &Task) -> Result<(String, String), (String, i32, i32)> {
    let child = Command::new("python")
        .args(["-m", "lagomorph", "execute", &task.id.to_string()])
        .env("DATABASE_URL", std::env::var("DATABASE_URL").unwrap_or_default())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| (format!("failed to spawn subprocess: {}", e), 0, 3))?;

    let output = child
        .wait_with_output()
        .await
        .map_err(|e| (format!("failed to wait: {}", e), 0, 3))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if output.status.success() {
        Ok((stdout.trim().to_string(), stderr.trim().to_string()))
    } else {
        Err((stderr.trim().to_string(), task.attempts, task.max_retries))
    }
}

async fn complete_task_in_db(
    client: &tokio_postgres::Client,
    task_id: Uuid,
    result: &str,
) -> Result<(), tokio_postgres::Error> {
    client
        .execute(
            "UPDATE lagomorph_tasks SET status = 'completed', result = $2, completed_at = now() WHERE id = $1",
            &[&task_id, &result],
        )
        .await?;
    Ok(())
}

async fn fail_task_in_db(
    client: &tokio_postgres::Client,
    task_id: Uuid,
    error: &str,
    attempts: i32,
    max_retries: i32,
) -> Result<(), String> {
    let new_attempts = attempts + 1;
    if new_attempts < max_retries {
        let backoff = std::cmp::min(10_i32.pow(new_attempts as u32), 600);
        client
            .execute(
                "UPDATE lagomorph_tasks SET status = 'pending', attempts = $2, error = $3, \
                 scheduled_at = now() + ($4::text || ' seconds')::interval, started_at = NULL, worker_id = NULL WHERE id = $1",
                &[&task_id, &new_attempts, &error, &backoff.to_string()],
            )
            .await
            .map_err(|e| e.to_string())?;
    } else {
        client
            .execute(
                "UPDATE lagomorph_tasks SET status = 'failed', attempts = $2, error = $3, completed_at = now() WHERE id = $1",
                &[&task_id, &new_attempts, &error],
            )
            .await
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_uuid_generation() {
        let id = Uuid::new_v4();
        assert_ne!(id.to_string().len(), 0);
    }

    #[test]
    fn test_task_serialization() {
        let task = Task {
            id: Uuid::new_v4(),
            queue_name: "test".into(),
            task_name: "test_fn".into(),
            module_path: "test_module".into(),
            args: serde_json::json!([1, 2, 3]),
            kwargs: serde_json::json!({"key": "value"}),
            status: "pending".into(),
            attempts: 0,
            max_retries: 3,
        };
        let json = serde_json::to_string(&task).unwrap();
        let deserialized: Task = serde_json::from_str(&json).unwrap();
        assert_eq!(task.id, deserialized.id);
        assert_eq!(task.task_name, deserialized.task_name);
    }
}
