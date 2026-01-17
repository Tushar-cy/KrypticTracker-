#!/usr/bin/env python3
"""Quick test to verify backend works."""

from backend.app import app

with app.test_client() as client:
    # Test main page
    r = client.get('/')
    print(f"✅ Main page: {r.status_code}")
    
    # Test API
    r2 = client.get('/api/stats', headers={'X-API-Key': 'local-dev-key-change-in-production'})
    print(f"✅ API stats: {r2.status_code}")
    if r2.status_code == 200:
        print(f"   Response: {r2.get_json()}")
    
    # Test live page
    r3 = client.get('/live')
    print(f"✅ Live page: {r3.status_code}")
    
    # Test insights
    r4 = client.get('/insights')
    print(f"✅ Insights page: {r4.status_code}")

print("\n🎉 All pages should return 200 (or at least not 500)!")



