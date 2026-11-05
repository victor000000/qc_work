//! Subcommand variants for the CLI.
use clap::Subcommand;
use std::path::PathBuf;

#[rustfmt::skip]
#[derive(Debug, Subcommand)]
pub enum Command {
    /// Initialize a new isolated strategy queue and result database.
    InitStrategy { #[arg(long)] strategy: String },
    /// Run the backtest server.
    Serve,
    /// Enqueue a backtest job.
    Queue {
        #[arg(long)] strategy: String, #[arg(long)] name: String,
        #[arg(long)] code_file: Option<PathBuf>,
        /// JSON object mapping extra Python filenames to source strings.
        #[arg(long)] extra_files: Option<PathBuf>,
        #[arg(long, conflicts_with = "code_file")] code_stdin: bool,
        #[arg(long)] batch: Option<String>, #[arg(long, default_value = "5")] priority: i64,
        #[arg(long)] description: Option<String>, #[arg(long)] hypothesis: Option<String>,
        #[arg(long)] based_on: Option<String>, #[arg(long)] project_id: Option<i64>,
    },
    /// Cancel a queued job (`--name`) or all queued (`CancelAll`).
    Cancel { #[arg(long)] strategy: String, #[arg(long)] name: String },
    CancelAll { #[arg(long)] strategy: String, #[arg(long)] batch: Option<String> },
    /// List queued/running jobs.
    List {
        #[arg(long)] strategy: Option<String>,
        #[arg(long, default_value = "queued,running")] status: String,
        #[arg(long)] batch: Option<String>, #[arg(long)] name_like: Option<String>,
        #[arg(long, default_value = "20")] limit: usize,
    },
    /// Recent errors / top by CAR/MDD / context / next experiment number.
    Errors {
        #[arg(long)] strategy: String, #[arg(long, default_value = "10")] limit: usize,
        #[arg(long)] detail: Option<String>,
    },
    Top {
        #[arg(long)] strategy: Option<String>, #[arg(long)] batch: Option<String>,
        #[arg(long, default_value = "20")] limit: usize,
    },
    Context { #[arg(long)] strategy: String },
    Next { #[arg(long)] strategy: String },
    /// Show one experiment's details (optionally with --code).
    Show {
        #[arg(long)] strategy: String, #[arg(long)] name: String,
        #[arg(long)] code: bool,
    },
    /// Remove old done/failed/cancelled queue entries.
    Clean {
        #[arg(long)] strategy: Option<String>,
        #[arg(long, default_value = "7")] older_than_days: i64,
        #[arg(long)] include_cancelled: bool, #[arg(long)] dry_run: bool,
    },
    /// Retry failed jobs (reset to queued).
    Retry {
        #[arg(long)] strategy: String,
        #[arg(long)] name: Option<String>, #[arg(long)] batch: Option<String>,
    },
    /// Show queue status / test QC API connectivity.
    Status,
    TestApi,
    CreateProjects { #[arg(long, default_value = "5")] count: usize },
    /// Delete projects past `--keep` in projects.json. `--sort-by`: `none`/`created`/`created_desc`.
    DeleteProjects {
        #[arg(long)] keep: usize, #[arg(long)] dry_run: bool,
        #[arg(long)] yes: bool, #[arg(long, default_value = "none")] sort_by: String,
    },
    /// Reconcile projects.json against QC; --prune-orphans removes IDs missing on QC.
    ReconcileProjects { #[arg(long)] prune_orphans: bool },
    /// List objects in the org Object Store at a prefix.
    ObjList { #[arg(long)] path: Option<String> },
    /// Get a download URL (or download to --out).
    ObjGet { #[arg(long)] key: String, #[arg(long)] out: Option<PathBuf> },
    /// Upload a local file to an object store key.
    ObjPut { #[arg(long)] key: String, #[arg(long)] file: PathBuf },
    /// Delete an object. --yes required to confirm.
    ObjDelete { #[arg(long)] key: String, #[arg(long)] yes: bool },
    /// Print object metadata (size, md5, mime, created, modified).
    ObjProps { #[arg(long)] key: String },
    /// Recursively walk a prefix and print per-category size breakdown.
    ObjStats { #[arg(long)] path: Option<String> },
    /// Recursively delete every key under a prefix (--yes to actually delete).
    ObjBulkDelete { #[arg(long)] prefix: String, #[arg(long)] yes: bool },
    /// Fetch the QC runtime console log for a backtest.
    BacktestLog {
        #[arg(long)] strategy: String, #[arg(long)] name: String,
        #[arg(long, default_value_t = 0)] start: i64, #[arg(long)] end: Option<i64>,
    },
    /// Print QC `runtimeStatistics` for a finished backtest (live fetch).
    BacktestStats { #[arg(long)] strategy: String, #[arg(long)] name: String },
    /// Fetch order history for a backtest. With --out, writes JSON; else prints summary.
    BacktestOrders {
        #[arg(long)] strategy: String, #[arg(long)] name: String,
        #[arg(long)] out: Option<PathBuf>,
    },
    /// Aggregate `runtimeStatistics` across all done experiments in a batch.
    BatchStats {
        #[arg(long)] strategy: String, #[arg(long)] batch: String,
        #[arg(long)] metrics: Option<String>,
    },
}
