//! Local HTTP fixtures; tests never need cloud credentials.
use super::QcClient;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

pub(crate) async fn mock_api(
    replies: Vec<(&'static str, &'static str)>,
) -> (QcClient, tokio::task::JoinHandle<()>) {
    mock_api_status(
        replies
            .into_iter()
            .map(|(path, body)| (path, 200, body))
            .collect(),
    )
    .await
}

pub(crate) async fn mock_api_status(
    replies: Vec<(&'static str, u16, &'static str)>,
) -> (QcClient, tokio::task::JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base_url = format!("http://{}", listener.local_addr().unwrap());
    let handle = tokio::spawn(async move {
        for (path, status, body) in replies {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut bytes = Vec::new();
            loop {
                let mut buffer = [0; 4096];
                let count = stream.read(&mut buffer).await.unwrap();
                assert!(count > 0, "request closed before headers");
                bytes.extend_from_slice(&buffer[..count]);
                if bytes.windows(4).any(|w| w == b"\r\n\r\n") {
                    break;
                }
            }
            let request = String::from_utf8_lossy(&bytes);
            assert!(request.starts_with(&format!("POST {path} ")), "{request}");
            let response = format!(
                "HTTP/1.1 {status} Fixture\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            );
            stream.write_all(response.as_bytes()).await.unwrap();
        }
    });
    let mut client = QcClient::new("test", "test");
    // Local fixtures must not traverse the developer's HTTP/SOCKS proxy.
    client.http = reqwest::Client::builder()
        .no_proxy()
        .connect_timeout(std::time::Duration::from_secs(2))
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap();
    client.base_url = base_url;
    (client, handle)
}
