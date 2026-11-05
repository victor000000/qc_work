use super::push_files;
use crate::client::test_support::mock_api;
use crate::db::QueueJob;

fn job(extra_files: Option<&str>) -> QueueJob {
    QueueJob {
        id: 1,
        name: "regression".into(),
        code: "pass".into(),
        extra_files: extra_files.map(str::to_owned),
        description: None,
        hypothesis: None,
        based_on: None,
        batch: None,
        requested_project_id: None,
        priority: 5,
        strategy: "test".into(),
    }
}

#[tokio::test]
async fn single_file_job_removes_previous_jobs_extra_sources() {
    let (client, server) = mock_api(vec![
        ("/files/read", r#"{"success":true,"files":[{"name":"main.py"},{"name":"old.py"},{"name":"library.py","isLibrary":true}]}"#),
        ("/files/delete", r#"{"success":true}"#),
        ("/files/update", r#"{"success":true}"#),
    ]).await;
    push_files(&client, None, 42, &job(None), "regression")
        .await
        .unwrap();
    server.await.unwrap();
}

#[tokio::test]
async fn reconciliation_failure_stops_upload() {
    let (client, server) = mock_api(vec![(
        "/files/read",
        r#"{"success":false,"errors":["denied"]}"#,
    )])
    .await;
    assert!(
        push_files(&client, None, 42, &job(None), "regression")
            .await
            .is_err()
    );
    server.await.unwrap();
}

#[test]
fn malformed_or_unsafe_extra_files_are_rejected() {
    for extra in [
        "not json",
        r#"{"../escape.py":"pass"}"#,
        r#"{"main.py":"override"}"#,
        r#"{"x.py":123}"#,
    ] {
        assert!(job(Some(extra)).validated_extra_files().is_err(), "{extra}");
    }
    assert_eq!(
        job(Some(r#"{"helpers.py":"pass"}"#))
            .validated_extra_files()
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn job_identity_includes_all_files_and_is_independent_of_json_key_order() {
    let first = job(Some(r#"{"a.py":"x=1","b.py":"y=2"}"#))
        .content_hash()
        .unwrap();
    let reordered = job(Some(r#"{"b.py":"y=2","a.py":"x=1"}"#))
        .content_hash()
        .unwrap();
    let changed = job(Some(r#"{"a.py":"x=3","b.py":"y=2"}"#))
        .content_hash()
        .unwrap();
    assert_eq!(first, reordered);
    assert_ne!(first, changed);
    assert_ne!(first, job(None).content_hash().unwrap());
}
