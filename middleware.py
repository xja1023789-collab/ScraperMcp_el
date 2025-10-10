import json
import base64
from urllib.parse import parse_qs, unquote

class SmitheryConfigMiddleware:
    def __init__(self, app,set_api_key):
        self.app = app
        self.set_api_key = set_api_key 

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http':
            query = scope.get('query_string', b'').decode()
            print(f"query1: {query}")
            
            if 'config=' in query:
                try:
                    config_b64 = unquote(parse_qs(query)['config'][0])
                    config = json.loads(base64.b64decode(config_b64))
                    print(f"config2: {config}")
                    
                    self.set_api_key(config)
                except Exception as e:
                    print(f"SmitheryConfigMiddleware: Error parsing config: {e}")
                    config=None
                    self.set_api_key(config)
            else:
                    self.set_api_key(config)
        
        await self.app(scope, receive, send)  
