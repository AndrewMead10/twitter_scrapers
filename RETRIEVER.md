# retriever.sh - Claude Code Skill

## Overview

retriever.sh exposes a project-scoped RAG API with three core operations:
1. **INGEST** a document
2. **QUERY** a project
3. **DELETE** a document vector

All operations require:
- `project_id` in the URL path
- `X-Project-Key` header for that project

Project IDs and keys are available in the retriever.sh Projects page.

## Configuration

### Required Environment Variables

```bash
RETRIEVER_PROJECT_ID=your-project-uuid
RETRIEVER_PROJECT_KEY=proj_...your_key...
```

### API Base URL

```text
https://retriever.sh
```

## API Reference

### 1. INGEST - Add a Document

**Endpoint:** `POST /api/rag/projects/{project_id}/documents`

**Headers:**
```text
X-Project-Key: {RETRIEVER_PROJECT_KEY}
Content-Type: application/json
```

**Request Body:**
```json
{
  "title": "Python Installation Guide",
  "text": "To install Python, visit python.org...",
  "metadata": {
    "source": "https://python.org/downloads/",
    "category": "docs"
  }
}
```

**Response:**
```json
{
  "id": 456,
  "content": "To install Python, visit python.org...",
  "title": "Python Installation Guide",
  "metadata": {
    "source": "https://python.org/downloads/",
    "category": "docs"
  },
  "created_at": "2025-01-20T18:42:11.214Z"
}
```

**Python Example:**
```python
import os
import requests

project_id = os.environ["RETRIEVER_PROJECT_ID"]
project_key = os.environ["RETRIEVER_PROJECT_KEY"]

payload = {
    "title": "Python Installation Guide",
    "text": "To install Python, visit python.org...",
    "metadata": {
        "source": "https://python.org/downloads/",
        "category": "docs",
    },
}

response = requests.post(
    f"https://retriever.sh/api/rag/projects/{project_id}/documents",
    headers={"X-Project-Key": project_key, "Content-Type": "application/json"},
    json=payload,
    timeout=30,
)
response.raise_for_status()
print(response.json())
```

### 2. QUERY - Hybrid Search

**Endpoint:** `POST /api/rag/projects/{project_id}/query`

**Headers:**
```text
X-Project-Key: {RETRIEVER_PROJECT_KEY}
Content-Type: application/json
```

**Request Body:**
```json
{
  "query": "How do I install Python?",
  "top_k": 5,
  "vector_k": 40
}
```

**Response:**
```json
{
  "results": [
    {
      "id": 456,
      "content": "To install Python, visit python.org...",
      "title": "Python Installation Guide",
      "metadata": {
        "source": "https://python.org/downloads/",
        "category": "docs"
      },
      "created_at": "2025-01-20T18:42:11.214Z"
    }
  ]
}
```

**Python Example:**
```python
import os
import requests

project_id = os.environ["RETRIEVER_PROJECT_ID"]
project_key = os.environ["RETRIEVER_PROJECT_KEY"]

response = requests.post(
    f"https://retriever.sh/api/rag/projects/{project_id}/query",
    headers={"X-Project-Key": project_key, "Content-Type": "application/json"},
    json={"query": "How do I install Python?", "top_k": 5, "vector_k": 40},
    timeout=30,
)
response.raise_for_status()
print(response.json()["results"])
```

### 3. DELETE - Remove a Document Vector

**Endpoint:** `DELETE /api/rag/projects/{project_id}/vectors/{document_id}`

**Headers:**
```text
X-Project-Key: {RETRIEVER_PROJECT_KEY}
```

**Response:** `204 No Content`

**Python Example:**
```python
import os
import requests

project_id = os.environ["RETRIEVER_PROJECT_ID"]
project_key = os.environ["RETRIEVER_PROJECT_KEY"]
document_id = 456

response = requests.delete(
    f"https://retriever.sh/api/rag/projects/{project_id}/vectors/{document_id}",
    headers={"X-Project-Key": project_key},
    timeout=30,
)
if response.status_code != 204:
    raise RuntimeError(f"Delete failed: {response.status_code} {response.text}")
```

## Error Handling

- `401`: missing or invalid `X-Project-Key`
- `404`: project or document not found
- `429`: query/ingest QPS rate limit exceeded
- `402`: plan capacity/limit reached

Always parse and surface the response `detail` field.

