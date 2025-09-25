# app/service/validation_service.py

import re
from typing import Optional, Dict, Any, Union, List
from flask import request


class ValidationService:
    """Service for validating and sanitizing API inputs to prevent injection attacks"""
    
    # Configuration constants
    MAX_QUERY_LENGTH = 1000
    MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
    
    ALLOWED_QUERY_TYPES = ['all', 'text', 'image', 'table']
    ALLOWED_YEARS = ['SARJANA', 'MAGISTER', 'DOKTOR', 'ALL']
    
    DANGEROUS_PATTERNS = [
        r'\$where',
        r'\$eval',
        r'javascript:',
        r'<script',
        r'function\s*\(',
        r'\{\s*\$',  # MongoDB operators
        r'eval\s*\(',
        r'setTimeout',
        r'setInterval',
    ]

    @classmethod
    def validate_query(cls, query: Any) -> Optional[str]:
        """Validate and sanitize query input"""
        if not query or not isinstance(query, str):
            return None
        
        # Remove potentially dangerous characters and limit length
        query = query.strip()
        if len(query) > cls.MAX_QUERY_LENGTH:
            return None
        
        # Remove control characters and other potentially dangerous chars
        query = re.sub(r'[\x00-\x1f\x7f]', '', query)
        
        # Basic injection pattern detection for NoSQL/vector queries
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return None
        
        return query

    @classmethod
    def validate_query_types(cls, raw: Any) -> str:
        """Parse and validate query types with whitelist validation"""
        if raw is None:
            return "all"
        
        if isinstance(raw, str):
            clean_val = raw.strip().lower()
            if clean_val in cls.ALLOWED_QUERY_TYPES:
                return clean_val
        
        return "all"

    @classmethod
    def validate_year(cls, year: Any) -> str:
        """Validate year parameter with whitelist"""
        if not year:
            return "all"
        
        if isinstance(year, str):
            year = year.strip().upper()
            if year in cls.ALLOWED_YEARS:
                return year
        
        return "all"

    @classmethod
    def validate_request_size(cls) -> bool:
        """Check if request size is within limits"""
        try:
            content_length = request.content_length or 0
            return content_length <= cls.MAX_REQUEST_SIZE
        except:
            return False

    @classmethod
    def validate_json_structure(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize JSON request structure"""
        if not isinstance(data, dict):
            return {}
        
        # Extract and validate only allowed keys
        validated = {}
        
        if 'query' in data:
            validated_query = cls.validate_query(data['query'])
            if validated_query:
                validated['query'] = validated_query
        
        if 'query_types' in data:
            validated['query_types'] = cls.validate_query_types(data['query_types'])
        
        if 'year' in data:
            validated['year'] = cls.validate_year(data['year'])
        
        return validated

    @classmethod
    def validate_api_request(cls) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Comprehensive API request validation"""
        
        # Check request size first
        if not cls.validate_request_size():
            return None, "Request size too large"
        
        if request.method == 'GET':
            # Validate GET parameters
            query = cls.validate_query(request.args.get('query'))
            if not query:
                return None, "Invalid or missing query parameter"
            from flask import current_app
            return {
                'query': query,
                'query_types': cls.validate_query_types(request.args.get('query_types', 'all')),
                'year': cls.validate_year(request.args.get('year', 'all')),
                'top_k': int(current_app.config["TOP_K"]),
                'context_expansion_window': 7
            }, None
            
        elif request.method == 'POST':
            # Validate JSON POST data
            try:
                data = request.get_json(silent=True) or {}
            except:
                return None, "Invalid JSON format"
            
            validated_data = cls.validate_json_structure(data)
            
            if not validated_data.get('query'):
                return None, "Invalid or missing query parameter"
            
            # Add defaults
            validated_data.setdefault('query_types', 'all')
            validated_data.setdefault('year', 'all')
            validated_data.setdefault('top_k', 15)
            validated_data.setdefault('context_expansion_window', 7)
            
            return validated_data, None
        
        return None, "Method not allowed"