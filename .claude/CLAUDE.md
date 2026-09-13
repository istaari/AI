# Project Memory & Conventions

<!-- Add project-specific conventions, architecture notes, and guidance for Claude here. -->

## Code Explorer Cache

### s3 — 2026-09-13
- **Scope:** package
- **Language:** Java / Kotlin
- `AwsS3Client` is a public interface; `AwsS3ClientImpl` lives in `internal/` — callers never import AWS SDK types directly
- `S3ClientFactory` (@Component) caches `S3Client` per `(accessKeyId, endpoint)` using Caffeine with TTL eviction and `close()` on eviction
- `AwsS3Properties` is a `@ConfigurationProperties` Java record with inline defaults (100 MB multipart threshold, 25 MB part size, 3 retries, 60 min client TTL)
- `AwsS3Exception` is an unchecked domain exception carrying `bucket` and `key` for log context
- `MultipartUploader` is a package-private static utility — streams large files in fixed-size chunks; aborts on any failure
- **Output:** docs/s3.md

### aicore — 2026-09-13
- **Scope:** package
- **Language:** Java / Kotlin
- Typed Java SDK over SAP AI Core `/v2` REST API: interface (`AiCoreClient`) + Spring `@Component` impl (`AiCoreClientImpl`) + endpoint enum (`AiCoreEndpoint`) + 56 DTOs
- All ML operations are scoped to a tenant resource group via `AI-Resource-Group` HTTP header; admin operations (Resource Group lifecycle) are tenant-level
- All DTOs use `@JsonIgnoreProperties(ignoreUnknown = true)` for resilience to AI Core API additions; timestamps stored as `String`
- AI Core list responses use envelope format `{"count": N, "resources": [...]}` — each resource type has a dedicated list wrapper class
- No pagination support — list methods return only the first page
- **Output:** docs/aicore.md

