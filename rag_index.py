import os
import re
import json
import uuid
import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI
import numpy as np

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

def load_docs():
    with open("character_docs.json", "r", encoding="utf-8") as f:
        return json.load(f)

def embed_text(text):
    res = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return res.data[0].embedding

def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# build index（第一次运行）
def build_index():
    docs = load_docs()
    index = []

    for char, content in docs.items():
        text = json.dumps(content, ensure_ascii=False)
        emb = embed_text(text)

        index.append({
            "character": char,
            "text": text,
            "embedding": emb
        })

    with open("vector_index.json", "w") as f:
        json.dump(index, f)

# query
def search(query, top_k=2):
    with open("vector_index.json", "r") as f:
        index = json.load(f)

    q_emb = embed_text(query)

    scored = []
    for item in index:
        score = cosine_sim(q_emb, item["embedding"])
        scored.append((score, item))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [x[1] for x in scored[:top_k]]

