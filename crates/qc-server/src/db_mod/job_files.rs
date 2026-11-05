//! Job file validation and reproducible content identity.
use super::QueueJob;
use std::collections::HashMap;

impl QueueJob {
    /// Hash the entire job specification, retaining legacy hashes for single-file jobs.
    ///
    /// # Errors
    /// Rejects invalid extra-file specifications.
    pub fn content_hash(&self) -> anyhow::Result<String> {
        use sha2::{Digest, Sha256};
        let extras = self.validated_extra_files()?;
        let bytes = if extras.is_empty() {
            self.code.as_bytes().to_vec()
        } else {
            let mut files: std::collections::BTreeMap<_, _> = extras.into_iter().collect();
            files.insert("main.py".to_string(), self.code.clone());
            serde_json::to_vec(&files)?
        };
        let digest = Sha256::digest(bytes);
        Ok(hex::encode(&digest[..8]))
    }

    /// Validate the complete file specification before mutating a shared project.
    ///
    /// # Errors
    /// Rejects malformed JSON and paths outside the project's Python sources.
    pub fn validated_extra_files(&self) -> anyhow::Result<HashMap<String, String>> {
        let files: HashMap<String, String> = match self.extra_files.as_deref() {
            None | Some("") => HashMap::new(),
            Some(json) => serde_json::from_str(json)?,
        };
        for (name, content) in &files {
            anyhow::ensure!(
                std::path::Path::new(name).extension() == Some(std::ffi::OsStr::new("py"))
                    && !name.starts_with('/')
                    && !name.contains('\\')
                    && !name.contains(':')
                    && name.split('/').all(|part| !matches!(part, "" | "." | "..")),
                "invalid extra file name: {name}"
            );
            anyhow::ensure!(name != "main.py", "extra_files cannot override main.py");
            anyhow::ensure!(
                content.len() <= 128_000,
                "extra file {name} exceeds size limit"
            );
        }
        Ok(files)
    }

    /// Parse `extra_files` into a `{filename: content}` map. `None`, empty, or
    /// invalid JSON all yield an empty map — so a malformed value can never
    /// break the single-file (main.py-only) push path.
    #[must_use]
    pub fn extra_files_map(&self) -> HashMap<String, String> {
        self.extra_files
            .as_deref()
            .filter(|s| !s.trim().is_empty())
            .and_then(|s| serde_json::from_str(s).ok())
            .unwrap_or_default()
    }
}
