#!/usr/bin/env python3
"""
Quick test script to debug Wablas API integration
"""
import asyncio
import httpx
import json

async def test_wablas_api():
    # Test data with hardcoded values
    api_key = "CheoAUw7edW9G0RQRoJuEtYZ1wJ9R0MNq86Xjz88wgRXKgb2AH0hiTW"
    secret_key = "II43pmFo"
    
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