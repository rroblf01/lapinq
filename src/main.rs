use clap::Parser;
use log::{error, info, warn};
use std::process::Stdio;
use std::sync::Arc;
use tokio::process::Command;
use tokio::sync::Semaphore;
use uuid::Uuid;

use _worker::{claim_task, complete_task_in_db, connect_db, ensure_schema, fail_task_in_db, Task};

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

#[tokio::main]
async fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    let args = Args::parse();
    let worker_id = Uuid::new_v4().to_string();

    info!(
        "Worker {} starting (concurrency={}, poll_interval={}s, timeout={}s)",
        worker_id, args.concurrency, args.poll_interval_secs, args.task_timeout_secs,
    );

    let client = connect_db(&args.database_url).await;
    ensure_schema(&client).await;

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
            fail_task_in_db(client, task.id, "timed out", task.attempts, task.max_retries)
                .await
                .map_err(|e| e.to_string())?;
            Ok(())
        }
    }
}

fn python_interpreter() -> String {
    std::env::var("LAGOMORPH_PYTHON").unwrap_or_else(|_| "python".to_string())
}

async fn run_python_subprocess(task: &Task) -> Result<(String, String), (String, i32, i32)> {
    let child = Command::new(python_interpreter())
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
