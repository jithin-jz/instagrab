# Test Webhook

Use this payload to simulate an Instagram mention webhook:

```json
{"object":"instagram","entry":[{"id":"17841400000000000","time":1715792400,"changes":[{"field":"mentions","value":{"media_id":"17912345678901234","comment_id":"18012345678901234","from":{"id":"17890000000000000","username":"johndoe"},"text":"@TargetAccount"}}]}]}
```

Compute a valid HMAC signature with your `IG_APP_SECRET`:

```bash
BODY='{"object":"instagram","entry":[{"id":"17841400000000000","time":1715792400,"changes":[{"field":"mentions","value":{"media_id":"17912345678901234","comment_id":"18012345678901234","from":{"id":"17890000000000000","username":"johndoe"},"text":"@TargetAccount"}}]}]}'
SECRET='your_meta_app_secret'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -binary | xxd -p -c 256)
```

Send the webhook with one curl command:

```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -H "X-Hub-Signature-256: sha256=$SIG" --data "$BODY"
```

The server should immediately return:

```json
{"status":"ok"}
```

For this test to complete the full pipeline, `media_id` must be replaced with a real media ID that your access token can read.
