"""
Utility functions for text processing
"""

import re

def escape_markdown(text: str) -> str:
    """Escape markdown special characters"""
    # Characters that need escaping in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    
    # Escape each character
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text