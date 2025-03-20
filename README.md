# FastAPI WebSocket Server with JWT Authentication

A simple FastAPI WebSocket server that uses JWT authentication to securely handle WebSocket connections. This server is designed to work alongside an existing Django REST API.

## Features

- JWT authentication for WebSocket connections
- Echo WebSocket consumer for testing
- Connection management for multiple clients
- Docker setup for both development and production
- CORS configuration to work with Django

## Prerequisites

- Docker and Docker Compose
- A Django application that can generate JWT tokens

## Getting Started

### Local Development

1. Clone this repository

   ```bash
   git clone https://github.com/your-username/fastapi-websocket-server.git
   cd fastapi-websocket-server
   ```

2. Start the WebSocket server with Docker Compose

   ```bash
   docker-compose up
   ```

3. The server will be available at `ws://localhost:8004/ws/{token}`

### Production Deployment

1. Build the Docker image

   ```bash
   docker build -t fastapi-websocket-server .
   ```

2. Run the container
   ```bash
   docker run -d -p 8004:8004 \
     -e JWT_SECRET=your_secret_key \
     --name websocket-server \
     fastapi-websocket-server
   ```

## JWT Token Generation

In your Django application, you need to create a view that generates JWT tokens for authenticated users. Here's an example implementation:

```python
# In your Django views.py
import jwt
import time
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect

@csrf_protect
def get_ws_token(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Create a short-lived token (5 minutes)
    payload = {
        "user_id": request.user.id,
        "username": request.user.username,
        "exp": int(time.time()) + 300  # 5 minutes expiration
    }

    # Sign with your Django SECRET_KEY
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    return JsonResponse({"token": token})
```

Make sure both the Django application and the WebSocket server use the same secret key for JWT.

## Testing

A simple HTML WebSocket test client is included in the project. Open `test_client.html` in your browser to test the WebSocket connection.

To use the test client:

1. Obtain a valid JWT token from your Django application
2. Enter the token in the input field
3. Click "Connect" to establish a WebSocket connection
4. Send messages to see them echoed back

## Environment Variables

- `JWT_SECRET`: Secret key for JWT validation (must match Django's key)
- `HOST`: Host to bind the server to (default: 0.0.0.0)
- `PORT`: Port to run the server on (default: 8000)

## Security Considerations

- Always use HTTPS in production for the initial WebSocket handshake
- Set appropriate CORS origins in `config.py`
- Use short-lived JWT tokens (5-15 minutes)
- Consider implementing token refresh for long-lived connections

## Integrating with Django

1. Add the token generation endpoint to your Django URLs:

   ```python
   urlpatterns = [
       # ... other URLs
       path('api/ws-token/', views.get_ws_token, name='ws-token'),
   ]
   ```

2. Add the WebSocket server URL to your frontend JavaScript:

   ```javascript
   // First get the token from Django
   fetch("/api/ws-token/")
     .then((response) => response.json())
     .then((data) => {
       // Connect to WebSocket with the token
       const socket = new WebSocket(`ws://your-server.com/ws/${data.token}`);
       // Handle WebSocket events
     });
   ```

3. Update the CORS settings in `config.py` to include your Django server URL:
   ```python
   cors_origins: list[str] = [
       "https://your-django-app.com",
       # Other allowed origins
   ]
   ```

## License

[MIT License](LICENSE)
