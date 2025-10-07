#!/usr/bin/env python3
"""
Quick test script to debug Wablas API integration
"""
import asyncio
import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def test_wablas_api():
    # Load credentials from .env
    api_key = os.getenv("WABLASS_API_KEY")
    secret_key = os.getenv("WABLASS_WEBHOOK_SECRET")

    if not api_key or not secret_key:
        print("Error: WABLASS_API_KEY or WABLASS_WEBHOOK_SECRET not set in .env")
        return
    
    api_url = 'https://sby.wablas.com/api/send-message'
    headers = {'Authorization': f"{api_key}.{secret_key}"}
    payload = {'phone': '6281234567890', 'message': 'Test message from debug script'}
    
    print(f"Testing Wablas API...")
    print(f"URL: {api_url}")
    print(f"Headers: Authorization=***")
    print(f"Payload: {payload}")
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            
            print(f"\nResponse status: {resp.status_code}")
            print(f"Response headers: {dict(resp.headers)}")
            print(f"Response text: {resp.text}")
            
            try:
                data = resp.json()
                print(f"Response JSON: {json.dumps(data, indent=2)}")
            except Exception as e:
                print(f"JSON parse error: {e}")
                
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_wablas_api())