#!/usr/bin/env python3
# Debug script to test form data handling

from flask import Flask, request
from frontend.app import app

def test_form_data():
    print("Testing form data handling...")
    
    with app.test_request_context(method='POST', data={
        'wikiLink': 'https://en.wikipedia.org/wiki/Test',
        'category': 'military'
    }):
        wiki_link = request.form.get("wikiLink")
        category = request.form.get("category")
        
        print(f"wikiLink: {wiki_link}")
        print(f"category: {category}")
        print(f"wikiLink type: {type(wiki_link)}")
        print(f"category type: {type(category)}")
        print(f"category is None: {category is None}")
        print(f"category is empty: {category == ''}")
        print(f"category length: {len(category) if category else 0}")

if __name__ == "__main__":
    test_form_data()
