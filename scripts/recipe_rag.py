#!/usr/bin/env python3
"""
Recipe Retrieval-Augmented Generation (RAG) Pipeline.

This module:
    1. Embeds a user query
    2. Searches recipe vectors in S3 Vectors
    3. Retrieves matching recipes from S3
    4. Builds a retrieval context
    5. Sends the context to Amazon Bedrock
    6. Returns a generated response
"""
import json
import boto3
import ingredient_slicer
import re

from scripts.recipe_embedding import RecipeEmbedding

system_prompt = """
You are a cooking assistant specializing in historic American recipes
from the late 18th to early 20th century.

The recipes come from the Feeding America Project (Michigan State University),
a digitized collection of approximately 76 historical American cookbooks.

Rules:
- Use ONLY the provided recipe context from the retrieved documents
- Do NOT use outside knowledge or invent metadata
- If metadata is missing, return "Unknown"
- Do NOT hallucinate ingredients, authors, or book details
- Preserve historical authenticity
- Only modernize instructions when explicitly requested

You will receive pre-ranked recipe results from a retrieval system.

Each recipe includes a Match Strength label:
- strong = direct title match (highest relevance)
- medium = ingredient-level match
- weak = semantic or partial match

Match Strength usage rules:
- Treat Match Strength as a ranking signal of relevance
- Do NOT reorder recipes unless information is missing or clearly inconsistent
- If no strong matches are present, explicitly acknowledge that results are weaker or approximate

Output rules:
- Always return recipes in the order provided
- Include Match Strength in the output for each recipe
"""


class RecipeRAG:
    """
    Retrieval-Augmented Generation pipeline for historic recipes.

    This class handles:
        - Query embedding
        - Vector similarity search
        - Recipe retrieval from S3
        - Context construction
        - Prompt generation
        - LLM response generation

    Attributes:
        s3: AWS S3 client.
        bedrock: AWS Bedrock Runtime client.
        vector_client: AWS S3 Vectors client.
        embedding_pipeline (RecipeEmbedding): Embedding utility class.
        source_bucket (str): S3 bucket containing cookbook JSON files.
        vector_bucket (str): S3 vector bucket name.
        index_name (str): S3 vector index name.
        model_id (str): Bedrock model ID.
    """

    def __init__(
        self,
        region="us-east-1",
        source_bucket="feeding-america-historic-cookbooks",
        vector_bucket="recipe-vector-bucket",
        index_name="recipe-index",
        model_id="amazon.nova-micro-v1:0"
    ):
        """
        Initialize AWS clients and RAG configuration.

        Args:
            region (str): AWS region name.
            source_bucket (str): S3 bucket containing cookbook JSON files.
            vector_bucket (str): S3 vector bucket name.
            index_name (str): Vector index name.
            model_id (str): Bedrock model ID.
        """
        self.s3 = boto3.client("s3", region_name=region)

        self.bedrock = boto3.client(
            "bedrock-runtime",
            region_name=region
        )

        self.vector_client = boto3.client(
            "s3vectors",
            region_name=region
        )

        self.embedding_pipeline = RecipeEmbedding(region=region)

        self.source_bucket = source_bucket
        self.vector_bucket = vector_bucket
        self.index_name = index_name
        self.model_id = model_id

    def get_historic_period(self, year):
        """
        Map a year to a named historic period.

        Args:
            year: Year value (int, str, or None).

        Returns:
            str: Historic period label, or "Unknown" if year is missing/invalid.
        """
        if year is None:
            return "Unknown"

        try:
            year = int(year)
        except (ValueError, TypeError):
            return "Unknown"

        if 1798 <= year <= 1829:
            return "Early Republic"

        elif 1830 <= year <= 1860:
            return "Antebellum"

        elif 1861 <= year <= 1865:
            return "Civil War Era"

        elif 1866 <= year <= 1899:
            return "Reconstruction and Gilded Age"

        elif 1900 <= year <= 1922:
            return "Progressive Era"

        return "Unknown"

    def calculate_lexical_score(self, query, recipe):
        """
        Lexical scoring between query and recipe.
        """

        query_recipe_obj = ingredient_slicer.IngredientSlicer(query)
        
        query_recipe_terms = [word.lower() for word in query_recipe_obj.food().split()]

    
        title = recipe.get("recipe_title", "").lower()
        ingredients = " ".join(recipe.get("recipe_ingredients", [])).lower()
    
        title_words = title.split()
        ingredient_words = ingredients.split()
    
        title_score = 0
        ingredient_score = 0
    
        # -------------------------
        # Word-frequency scoring
        # -------------------------
        #print("QUERY TERMS", query_recipe_terms)
        for term in query_recipe_terms:
            for word in term.split():
    
                # title match (strong signal)
                title_score += title_words.count(word) * 10
    
                # ingredient match (weaker signal)
                ingredient_score += ingredient_words.count(word) * 2
    
        # -------------------------
        # Final score 
        # -------------------------
        match_score = title_score + ingredient_score

        #strong match if > 2 query terms match the title. >10 points
        if title_score > 10 and ingredient_score > 0:
            match_strength = "strong"
        elif title_score <= 10 and ingredient_score > 0:
            match_strength = "medium"
        else:
            match_strength = "weak"

        # print("RECIPE:", recipe["recipe_title"])
        # print("TITLE SCORE:", title_score)
        # print("ING SCORE:", ingredient_score)
        # print("LEX SCORE:", match_score)
        # print("MATCH STRENGTH: ", match_strength)
        
    
        return match_score, match_strength

    def retrieve_recipes(self, query, n_recipes=3):

        top_k = 25
        
        query_embedding = self.embedding_pipeline.embed_text(query)

        response = self.vector_client.query_vectors(
            vectorBucketName=self.vector_bucket,
            indexName=self.index_name,
            queryVector={"float32": query_embedding},
            topK=top_k,
            returnMetadata=True
        )
    
        vectors = response.get("vectors", [])
        cookbook_cache = {}
        recipes = {}
    
    
    
        # -------------------------
        # Build candidates
        # -------------------------
        for i, vector in enumerate(vectors):
    
            metadata = vector.get("metadata", {})
            recipe_id = metadata.get("recipe_id")
            s3_key = metadata.get("s3_key")
    
            if not recipe_id or not s3_key:
                continue
    
            # -------------------------
            # Load cookbook (cached)
            # -------------------------
            if s3_key not in cookbook_cache:
                obj = self.s3.get_object(
                    Bucket=self.source_bucket,
                    Key=s3_key
                )
                cookbook_cache[s3_key] = json.loads(
                    obj["Body"].read().decode("utf-8")
                )
    
            cookbook = cookbook_cache[s3_key]
            recipe = cookbook["recipes"].get(recipe_id)
    
            if not recipe:
                continue
    
            # -------------------------
            # Lexical score
            # -------------------------
            lexical_score, strength = self.calculate_lexical_score(query, recipe)
    
            # -------------------------
            # Vector rank boost
            # -------------------------
            vector_rank = i + 1
            vector_bonus = top_k - vector_rank
    
            # -------------------------
            # FINAL HYBRID SCORE
            # -------------------------
            final_score = lexical_score + vector_bonus
    
            recipes[recipe_id] = {
                "vector_rank": vector_rank,
                "lexical_score": lexical_score,
                "vector_bonus": vector_bonus,
                "final_score": final_score,
                "match_strength": strength,
                "recipe": recipe,
                "book_metadata": cookbook.get("metadata", {})
            }
    
        # -------------------------
        # Sort by final score
        # -------------------------
        sorted_recipes = dict(
            sorted(
                recipes.items(),
                key=lambda item: item[1]["final_score"],
                reverse=True
            )
        )

    
        return dict(list(sorted_recipes.items())[:n_recipes])

    def build_context(self, recipes):
        """
        Build LLM context string from retrieved recipes.

        Args:
            recipes (dict): Retrieved recipe dictionary.

        Returns:
            str: Formatted context string.
        """
        context_parts = []

        for recipe_id, data in recipes.items():

            recipe = data["recipe"]
            book_meta = data.get("book_metadata", {})
            book_year = book_meta.get("book_year")

            if book_year is not None:
                match = re.search(r"\b(\d{4})\b", str(book_year))
                book_year = match.group(1) if match else None

            historic_period = self.get_historic_period(book_year)

            context_parts.append(
                f"""
                    Title: {recipe.get('recipe_title', 'Unknown')}
                    Match Score: {data['final_score']}
                    Lexical Score: {data['lexical_score']}
                    Vector Rank: {data['vector_rank']}
                    Match Strength: {data['match_strength']}
                    Book: {book_meta.get('book_title', 'Unknown')}
                    Author: {book_meta.get('book_creator', 'Unknown')}
                    Year: {book_meta.get('book_year', 'Unknown')}
                    Historic Period: {historic_period}

                    Ingredients:
                    {', '.join(recipe.get('recipe_ingredients', []))}

                    Original Instructions:
                    {recipe.get('recipe_instructions', 'Unknown')}
                    """
            )

        return "\n".join(context_parts)

    def build_user_prompt(self, query, context, n_recipes):
        """
        Build the user prompt for the LLM.
        """
    
        return f"""
            You are a recipe retrieval assistant.
            
            You will be given historical cookbook recipes retrieved from a search system.
            
            Your task is to return the top {n_recipes} most relevant recipes that best answer the user's question.
            
            ---
            
            # CONTEXT (RECIPES)
            
            {context}
            
            ---
            
            # USER QUESTION
            
            {query}
            
            ---
            
            # OUTPUT FORMAT
            
            Return ONLY valid Markdown.
            
            For each recipe, use the following structure exactly:
            
            ## Recipe X
            
            **Title:**  
            ...
            
            **Book:**  
            ...
            
            **Author:**  
            ...
            
            **Year Published:**  
            ...
            
            **Headnote:**  
            Write a brief 1-2 sentence summary describing the recipe and its historical significance.
            
            **Ingredients:**
            
            - Ingredient 1
            - Ingredient 2
            - Ingredient 3
            
            **Original Instructions:**
            
            (Original recipe instructions exactly as provided.)
            
            **Modern Instructions:**
            
            1. Rewrite the instructions using modern cooking language.
            2. Preserve the original ingredients and intent.
            3. Use numbered steps.
            4. Do not invent ingredients that are not present in the recipe.
            
            ---
            
            # RULES
            
            - Return up to {n_recipes} recipes in the order provided.
            - Use the exact field names shown above.
            - Keep formatting identical for every recipe.
            - Do not skip fields.
            - If information is unavailable, write "N/A".
            - Do not add introductions, conclusions, commentary, or explanations.
            - Do not mention retrieval systems, ranking algorithms, embeddings, vector search, or scoring methods.
            - Return Markdown only.
            """

    def generate_response(self, user_prompt):
        """
        Generate an LLM response using Amazon Bedrock Converse API.

        Args:
            user_prompt (str): User prompt sent to the model.

        Returns:
            str: Generated LLM response text.
        """
        response = self.bedrock.converse(
            modelId=self.model_id,
            system=[
                {"text": system_prompt}
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"text": user_prompt}
                    ]
                }
            ],
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.3  # Low temp = more faithful to historical content
            }
        )

        return response["output"]["message"]["content"][0]["text"]

    def run_rag(self, query, n_recipes=3):
        """
        Execute the full RAG pipeline.

        Args:
            query (str): User question.
            n_recipes (int): Number of recipes to retrieve.

        Returns:
            str: Generated response from the LLM.
        """
        recipes = self.retrieve_recipes(
            query=query,
            n_recipes=n_recipes
        )

        context = self.build_context(recipes)

        user_prompt = self.build_user_prompt(
            query=query,
            context=context,
            n_recipes=n_recipes
        )

        return self.generate_response(user_prompt)


if __name__ == "__main__":
    recipe_rag = RecipeRAG()
    print(recipe_rag.run_rag("beef soup"))