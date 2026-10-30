# CBrowser Supervisor Gateway Fixture Contract

This specification defines the contract of the public `SupervisorGatewayFixture` for Supervisor E2E test suites and Root container blackbox integration tests.

## 1. Overview & Class Definition

```python
class SupervisorGatewayFixture:
    def __init__(
        self,
        port: int,
        credentials: AgentCredentials,
        token_file: Path,
    ) -> None:
        ...
```

- **Host Binding**: Always binds `127.0.0.1:{port}`.
- **`control_url`**: `http://127.0.0.1:{port}` (used by `GatewayControlClient` / `--gateway-control-url`).
- **`gateway_url`**: `ws://host.docker.internal:{port}` (used by Stream container Agent / `--gateway-url`).
- **`credentials`**: Instance of `cbrowser.supervisor.agent_credentials.AgentCredentials`, loaded from external random key file (`--agent-key-file`).
- **`token_file`**: Path to external token file containing >= 32-byte secret for internal control RPC authentication.

## 2. Stream Agent Registration WebSocket Route

- **Endpoint**: `GET /stream/agent/register` (WebSocket)
- **Authentication**:
    - Request header: `Authorization: Bearer <token>`
    - The raw bearer token is validated against `credentials.verify(token, profile_id, runtime_instance_id)` derived from the shared secret key.
    - Invalid bearer: rejected with WebSocket close code `1008` (Policy Violation).
- **Registration Handshake**:
    - Agent sends text JSON frame:
        ```json
        {
          "version": "v2",
          "action": "register",
          "profile_id": "<profile_id>",
          "runtime_instance_id": "<runtime_instance_id>",
          "udp_port": 30000,
          ...
        }
        ```
    - Fixture records the active agent mapping: `profile_id -> (instance_id, agent_session_id, ws)`.
    - Fixture sends registration confirmation frame:
        ```json
        {
          "version": "v2",
          "status": "ok",
          "profile_id": "<profile_id>",
          "runtime_instance_id": "<runtime_instance_id>",
          "agent_session_id": "<uuid-v4>"
        }
        ```
    - Upon disconnect or socket closure, the fixture unregisters the agent if it is the current socket for that profile.

## 3. Internal Control RPC Routes (Supervisor -> Gateway)

All internal control routes enforce:

1. **Bearer Token Authentication**:
    - Header: `Authorization: Bearer <token>`
    - Constant-time comparison (`hmac.compare_digest`) against the external token in `token_file`.
    - Missing or mismatch: HTTP `401 Unauthorized`.
2. **Instance Fencing**:
    - Compares the request's `runtime_instance_id` against the registered Agent's current `instance_id`.
    - If no agent is registered for `profile_id`: HTTP `503 Service Unavailable` (no fake ok).
    - If `runtime_instance_id` does not match the active agent: HTTP `409 Conflict`.

### 3.1 Visibility Route

- **Endpoint**: `GET /gateway/v1/internal/profiles/{profile_id}/visibility?runtime_instance_id={runtime_instance_id}`
- **Behavior**:
    - Checks whether any active viewer WebSocket for `profile_id` is in foreground.
    - Defaults to `{"has_foreground_viewers": false}` when zero viewers exist.
- **Success Response**: HTTP `200 OK`
    ```json
    {
      "has_foreground_viewers": false
    }
    ```

### 3.2 Quota Route

- **Endpoint**: `POST /gateway/v1/internal/profiles/{profile_id}/quota`
- **Request Body**:
    ```json
    {
      "runtime_instance_id": "<runtime_instance_id>",
      "max_fps_cap": 15.0
    }
    ```
- **Behavior**:
    - Verifies instance fence.
    - Forwards control envelope to the registered Stream Agent WebSocket:
        ```json
        {
          "version": "v2",
          "action": "supervisor_quota",
          "profile_id": "<profile_id>",
          "runtime_instance_id": "<runtime_instance_id>",
          "agent_session_id": "<agent_session_id>",
          "payload": {
            "max_fps_cap": 15.0
          }
        }
        ```
- **Success Response**: HTTP `200 OK`
    ```json
    {
      "status": "ok"
    }
    ```

### 3.3 Disconnect Viewers Route

- **Endpoint**: `POST /gateway/v1/internal/profiles/{profile_id}/disconnect`
- **Request Body**:
    ```json
    {
      "runtime_instance_id": "<runtime_instance_id>"
    }
    ```
- **Behavior**:
    - Verifies instance fence.
    - Closes all active Viewer WebSockets for `profile_id` with WebSocket close code `1000`.
    - **Does NOT** disconnect the Stream Agent WebSocket.
- **Success Response**: HTTP `200 OK`
    ```json
    {
      "status": "ok"
    }
    ```

## 4. Test Viewer WebSocket Route

- **Endpoint**: `GET /viewer/{profile_id}?foreground=true|false`
- **Behavior**:
    - Test harness viewer WebSocket connection simulating browser clients.
    - Dynamically updates foreground viewer set for visibility verification.
    - Closed immediately when `POST /disconnect` is triggered for this `profile_id`.

## 5. Lifecycle Management

- `async def start() -> None`: Starts aiohttp server on `127.0.0.1:{port}`.
- `async def stop() -> None`: Closes all viewer sockets, all agent sockets, shuts down aiohttp runner cleanly in a `try...finally` block.
- Supports `async with SupervisorGatewayFixture(...) as gw:` context management.
