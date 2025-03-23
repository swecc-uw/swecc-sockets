import jwt
import os
import time
import argparse
import json

def generate_token(user_id, username, secret_key, expiration_minutes=5):
    payload = {
        "user_id": user_id,
        "username": username,
        "groups": ["is_authenticated"],
        "exp": int(time.time()) + (expiration_minutes * 60)
    }
    
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a test JWT token")
    parser.add_argument("--user-id", type=int, default=1, help="User ID")
    parser.add_argument("--username", type=str, default="testuser", help="Username")
    parser.add_argument("--secret", type=str, default="secret",
                        help="Secret key (must match JWT_SECRET in the server)")
    parser.add_argument("--minutes", type=int, default=60, 
                        help="Token expiration time in minutes")
    parser.add_argument("--verbose", action="store_true", help="Print debug info")
    
    args = parser.parse_args()
    
    token = generate_token(
        args.user_id, 
        args.username, 
        os.getenv("JWT_SECRET", args.secret),
        args.minutes
    )
    
    if args.verbose:
      print("\n=== JWT Token for Testing ===")
      print(f"\nUsing secret: {args.secret}")
      print(f"\nToken: {token}")
      decoded = jwt.decode(token, args.secret, algorithms=["HS256"])
      print(f"\nDecoded payload: {json.dumps(decoded, indent=2)}")
      print(f"\nExpires at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(decoded['exp']))}")

      print("\nUse this token in the test client or with WebSocket clients.")
      print("Example WebSocket URL: ws://localhost:8004/ws/" + token)
    else:
      print(token)