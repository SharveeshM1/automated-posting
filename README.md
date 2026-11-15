# Automated Multi-Platform Posting System

A FastAPI service that takes one short message containing a single CTA link and publishes it to several third-party platforms through their official APIs. Each platform is handled independently, so one failure never blocks the others.

## Platforms

| Platform | API used | Credentials | Post URL | Public check |
| --- | --- | --- | --- | --- |
| [Bluesky](https://docs.bsky.app/docs/api/com-atproto-repo-create-record) | AT Protocol `createSession` + `createRecord` (link added as a rich-text facet so it is clickable) | handle + app password | `bsky.app/profile/<handle>/post/<rkey>` | unauthenticated `getPosts` on the public AppView |
| [Mastodon](https://docs.joinmastodon.org/methods/statuses/#create) | `POST /api/v1/statuses` (`visibility: public`) | instance + access token | URL returned by the API | unauthenticated `GET /api/v1/statuses/:id` |
| [DEV Community](https://developers.forem.com/api/v1#tag/articles/operation/createArticle) | `POST /api/articles` (published) | API key | URL returned by the API | anonymous `GET`, requiring the first 25 characters of the link-free message text in the HTML |
| [GitHub Gist](https://docs.github.com/en/rest/gists/gists#create-a-gist) | `POST /gists` (`public: true`) | token with `gist` scope | `html_url` from the API | `public` flag + anonymous `GET`, requiring the first 25 characters of the link-free message text in the HTML |
| [GitLab Snippets](https://docs.gitlab.com/api/snippets/) | `POST /api/v4/snippets` (`visibility: public`) | personal access token with `api` scope | `web_url` returned by the API | unauthenticated `GET` of the raw file, requiring the first 25 characters of the link-free message |

A platform whose credentials are missing is reported as `failed` with `Not configured: set ...` and the rest still run. Platform selection is internal: the request only contains `message`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the platforms you want to use
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Interactive docs: <http://localhost:4000/docs>

`.env` is git-ignored. Only `.env.example` (no secrets) is committed.

### Getting credentials

- **Bluesky**: Settings → Privacy and security → App passwords. Use the app password, never your main password.
- **Mastodon**: Preferences → Development → New application, scope `write:statuses`; copy the access token.
- **DEV**: Settings → Extensions → DEV Community API Keys.
- **GitHub**: personal access token with the `gist` scope.
- **GitLab Snippets**: create a personal access token with the `api` scope at gitlab.com → Edit profile → Access tokens.

## API

### `POST /posting`

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message": "Check out our latest business platform and grow your online visibility. https://example.com"}'
```

Validation rules:

- non-empty, at most **200 characters** (after trimming)
- **exactly one** link, and it must start with `http://` or `https://`
- the link must be a valid URL (real hostname with a TLD or an IPv4 address, valid port, no embedded credentials); trailing sentence punctuation such as `.` or `)` is not treated as part of the link

Invalid input returns `422`:

```json
{
  "success": false,
  "errors": [
    {
      "field": "message",
      "error": "Message must contain exactly one CTA link starting with http:// or https:// (found 2)."
    }
  ]
}
```

A valid request always returns `200` with one entry per platform. `success` is `true` when at least one platform succeeded.

Live response from 15 Nov 2026:

```json
{
  "success": true,
  "results": [
    {
      "platform": "Bluesky",
      "status": "success",
      "posted_url": "https://bsky.app/profile/sharveesh.bsky.social/post/3n2e42bn6rl2f",
      "public_access": true,
      "date": "2026-11-15",
      "time": "13:18:50",
      "error": null
    },
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@Sharveesh/117620652670000046",
      "public_access": true,
      "date": "2026-11-15",
      "time": "13:18:48",
      "error": null
    },
    {
      "platform": "DEV Community",
      "status": "success",
      "posted_url": "https://dev.to/sharveesh_m_06995223a05de/check-out-our-latest-business-platform-and-grow-your-online-visibility-1a02",
      "public_access": true,
      "date": "2026-11-15",
      "time": "13:18:48",
      "error": null
    },
    {
      "platform": "GitHub Gist",
      "status": "success",
      "posted_url": "https://gist.github.com/SharveeshM1/496e54b025a2b82de1aed30a94d5f5e4",
      "public_access": true,
      "date": "2026-11-15",
      "time": "13:18:49",
      "error": null
    },
    {
      "platform": "GitLab Snippets",
      "status": "success",
      "posted_url": "https://gitlab.com/-/snippets/6079061",
      "public_access": true,
      "date": "2026-11-15",
      "time": "13:18:49",
      "error": null
    }
  ]
}
```

Live run on 15 Nov 2026: all 5 platforms posted successfully with public_access true.

`date` and `time` are UTC. `public_access` is checked **after** posting, without credentials, so it reflects what an anonymous visitor can see. For DEV Community and GitHub Gist, the check also confirms the page contains the first 25 characters of the message text after removing the link and HTML-unescaping the page. GitLab Snippets is checked against its raw file.

Example of a real response from a machine with no credentials configured (and no internet access):

```json
{
  "platform": "Bluesky",
  "status": "failed",
  "posted_url": null,
  "public_access": false,
  "date": null,
  "time": null,
  "error": "Not configured: set BLUESKY_HANDLE, BLUESKY_APP_PASSWORD"
}
```

## Project structure

```
app/
├── main.py                  FastAPI app, /posting endpoint, validation error format
├── schemas.py               Pydantic request/response models
├── links.py                 CTA link extraction + URL validation
├── config.py                Environment-based settings
├── platforms/
│   ├── base.py              Platform interface, shared error handling
│   ├── bluesky.py  mastodon.py  devto.py  github_gist.py  gitlab_snippet.py
│   └── __init__.py          Registry: add a platform by adding one class here
└── services/
    └── posting_service.py   Runs all platforms concurrently, isolates failures
tests/
├── test_posting.py          Validation + failure-isolation tests
└── test_platforms.py        Per-platform request/response tests (mock HTTP)
```

## Design notes

- **Failure isolation**: platforms run concurrently with `asyncio.gather`; each is wrapped so a rejection, timeout, network error or unexpected payload becomes a `failed` entry instead of an exception.
- **No secrets in output**: API errors are built from the response body, not from httpx exceptions; GitLab tokens are redacted from error messages.
- **Adding a platform**: subclass `Platform`, implement `publish()`, declare `required_settings`, and register it in `platforms/__init__.py`.

## Tests

```bash
pytest
```

The platform tests use `httpx.MockTransport` to check the request each integration builds (endpoint, headers, payload, Bluesky link-facet byte offsets) and how it parses the documented response. They do not call the live services, so run the app once with your own credentials to confirm each integration end to end.

## Logs

The application writes logs to the console where Uvicorn is running.
