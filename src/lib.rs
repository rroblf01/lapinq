use deadpool_postgres::{Config, ManagerConfig, Pool, RecyclingMethod, Runtime};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: Uuid,
    pub queue_name: String,
    pub task_name: String,
    pub module_path: String,
    pub args: serde_json::Value,
    pub kwargs: serde_json::Value,
    pub status: String,
    pub attempts: i32,
    pub max_retries: i32,
    pub priority: i32,
}

const SCHEMA_SQL: &str = "
    CREATE TABLE IF NOT EXISTS lapinq_tasks (
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
        priority     INT NOT NULL DEFAULT 0,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at   TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        last_heartbeat TIMESTAMPTZ,
        worker_id    TEXT
    );
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;
    ALTER TABLE lapinq_tasks ADD COLUMN IF NOT EXISTS ttl_seconds INT;
    CREATE INDEX IF NOT EXISTS idx_tasks_status
        ON lapinq_tasks(status, created_at);
    CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
        ON lapinq_tasks(scheduled_at)
        WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
        ON lapinq_tasks(priority DESC, created_at)
        WHERE status = 'pending';
";

pub async fn connect_db(database_url: &str) -> Pool {
    let mut cfg = Config::new();
    cfg.url = Some(database_url.to_string());
    cfg.manager = Some(ManagerConfig {
        recycling_method: RecyclingMethod::Fast,
    });
    cfg.create_pool(Some(Runtime::Tokio1), tokio_postgres::NoTls)
        .expect("Failed to create PostgreSQL connection pool")
}

pub async fn ensure_schema(pool: &Pool) {
    let client = pool.get().await.expect("Failed to get connection");
    client
        .batch_execute(SCHEMA_SQL)
        .await
        .expect("Failed to create schema");
}

pub async fn claim_task(
    pool: &Pool,
    worker_id: &str,
) -> Result<Option<Task>, Box<dyn std::error::Error>> {
    let client = pool.get().await?;
    let row = client
        .query_opt(
            "
            UPDATE lapinq_tasks
            SET status = 'running',
                started_at = now(),
                worker_id = $1,
                last_heartbeat = now()
            WHERE id = (
                SELECT id FROM lapinq_tasks
                WHERE status = 'pending'
                AND scheduled_at <= now()
                ORDER BY priority DESC, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, queue_name, task_name, module_path, args, kwargs, status, attempts, max_retries, priority
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
            priority: r.get(9),
        })),
        None => Ok(None),
    }
}

pub async fn complete_task_in_db(
    pool: &Pool,
    task_id: Uuid,
    result: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let client = pool.get().await?;
    client
        .execute(
            "UPDATE lapinq_tasks SET status = 'completed', result = $2, completed_at = now() WHERE id = $1",
            &[&task_id, &result],
        )
        .await?;
    Ok(())
}

pub async fn fail_task_in_db(
    pool: &Pool,
    task_id: Uuid,
    error: &str,
    attempts: i32,
    max_retries: i32,
) -> Result<(), String> {
    let client = pool.get().await.map_err(|e| e.to_string())?;
    let new_attempts = attempts + 1;
    if new_attempts < max_retries {
        let backoff = retry_backoff_seconds(new_attempts);
        client
            .execute(
                "UPDATE lapinq_tasks SET status = 'pending', attempts = $2, error = $3, \
                 scheduled_at = now() + ($4::text || ' seconds')::interval, started_at = NULL, worker_id = NULL WHERE id = $1",
                &[&task_id, &new_attempts, &error, &backoff.to_string()],
            )
            .await
            .map_err(|e| e.to_string())?;
    } else {
        client
            .execute(
                "UPDATE lapinq_tasks SET status = 'failed', attempts = $2, error = $3, completed_at = now() WHERE id = $1",
                &[&task_id, &new_attempts, &error],
            )
            .await
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

pub async fn heartbeat_worker(
    pool: &Pool,
    worker_id: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let client = pool.get().await?;
    client
        .execute(
            "UPDATE lapinq_tasks SET last_heartbeat = now() WHERE worker_id = $1 AND status = 'running'",
            &[&worker_id],
        )
        .await?;
    Ok(())
}

pub fn retry_backoff_seconds(attempt: i32) -> i32 {
    let backoffs = [10, 30, 60, 300, 600];
    let idx = (attempt - 1) as usize;
    if attempt <= 0 {
        0
    } else if idx >= backoffs.len() {
        backoffs[backoffs.len() - 1]
    } else {
        backoffs[idx]
    }
}

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyfunction]
fn execute_task_inline(py: Python, task_data: &Bound<'_, PyAny>) -> PyResult<String> {
    let module_path: String = task_data.get_item("module_path")?.extract()?;
    let task_name: String = task_data.get_item("task_name")?.extract()?;

    let module = py.import(module_path.as_str())?;
    let func_name = task_name.rsplit('.').next().unwrap_or(&task_name);
    let func = module.getattr(func_name)?;

    let inspect = py.import("inspect")?;
    let is_coro: bool = inspect
        .call_method1("iscoroutinefunction", (&func,))?
        .extract()?;
    if is_coro {
        return Err(PyTypeError::new_err(
            "async function requires Python executor",
        ));
    }

    let args_list = task_data.get_item("args")?;
    let args_vec: Vec<PyObject> = args_list.extract()?;
    let args_tuple = pyo3::types::PyTuple::new(py, &args_vec)?;

    let kwargs_bound = task_data.get_item("kwargs")?;
    let kwargs_dict = kwargs_bound.downcast::<PyDict>()?;

    let result = func.call(args_tuple, Some(kwargs_dict))?;

    let json_mod = py.import("json")?;
    let result_str: String = json_mod
        .call_method1("dumps", (result,))?
        .extract()?;
    Ok(result_str)
}

#[pymodule]
fn _worker(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(execute_task_inline, m)?)?;
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
            priority: 0,
        };
        let json = serde_json::to_string(&task).unwrap();
        let deserialized: Task = serde_json::from_str(&json).unwrap();
        assert_eq!(task.id, deserialized.id);
        assert_eq!(task.task_name, deserialized.task_name);
    }
}
