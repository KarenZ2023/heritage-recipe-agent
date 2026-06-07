# Historic Recipe Explorer

## Overview

Historic Recipe Explorer is a Retrieval-Augmented Generation (RAG) application that enables users to search and explore historic American cookbooks using natural language. Instead of manually browsing thousands of pages, users can ask questions about ingredients, dishes, cooking methods, or historical food trends and receive relevant recipes sourced directly from historic texts.

Visit the [Historic Reciper Explorer App](https://historic-recipe-explorer.streamlit.app/) to ask questions about historic recipes.

<img width="1272" height="890" alt="image" src="https://github.com/user-attachments/assets/dd7511a8-c03e-49c4-bf35-35a58e6b10c8" />

## Dataset

This project uses recipes from Feeding America: The Historic American Cookbook Dataset, a collection of 76 historic American cookbooks spanning the 18th and 19th centuries.

The dataset includes:

* Cookbook metadata (title, author, publication year, publisher)
* Recipe titles
* Ingredients
* Instructions
* Historical context and classification information

Each cookbook is stored as a structured JSON file containing recipe and book-level metadata.

## Features

* Natural language recipe search
* Semantic retrieval using vector embeddings
* Hybrid ranking combining vector similarity and lexical matching
* Source-grounded responses based on historic recipes
* Interactive Streamlit user interface

## Architecture

### Ingestion Pipeline

1. Load cookbook JSON files from Amazon S3
2. Process recipes individually
3. Generate embeddings for each recipe
4. Store vectors and metadata in Amazon S3 Vectors
5. Track processed recipes to avoid duplicate ingestion

### Retrieval Pipeline

1. Convert the user's query into an embedding
2. Retrieve candidate recipes using vector similarity search
3. Apply lexical scoring to improve relevance
4. Rank recipes using a hybrid scoring approach
5. Pass the highest-ranking recipes to the language model as context

### Response Generation

Retrieved recipes are supplied to a large language model, which generates answers grounded in the cookbook content while preserving historical context.

## Technology Stack

* Python
* Amazon Bedrock
* Amazon S3
* Amazon S3 Vectors
* Streamlit
* boto3

## Example Queries

* What oyster recipes were popular in the late 1800s?
* Find historic recipes that use apples and cinnamon.
* Show me soup recipes from historic American cookbooks.
* How was chicken prepared?

## Project Structure

```text
project/
│
├── scripts/
│   ├── parse_recipes.py         # Parse XML cookbook files into structured JSON
│   ├── recipe_embedding.py      # Generate recipe embeddings and store vectors
│   ├── recipe_rag.py            # Retrieval and generation pipeline
│   ├── recipe_api.py            # FastAPI service for recipe retrieval
│   └── recipe_app.py            # Streamlit user interface
│
├── notebooks/                  # Development and experimentation notebooks
│
├── embedded_recipe_ids.json    # Tracks embedded recipes and prevents duplicate ingestion
│
└── README.md
```

