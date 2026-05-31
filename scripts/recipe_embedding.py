#!/usr/bin/env python3

import argparse
import json
import os
import time

import boto3
from botocore.exceptions import ClientError


class RecipeEmbedding:
    """
    Handles embedding cookbook recipes into AWS S3 Vectors using
    Amazon Titan Embeddings.

    This class:
        - Loads cookbook JSON files from S3
        - Generates embeddings for each recipe
        - Stores vectors in S3 Vectors
        - Tracks already embedded recipes locally

    Attributes:
        s3: AWS S3 client.
        bedrock: AWS Bedrock Runtime client.
        vector_client: AWS S3 Vectors client.
        tracker_path (str): Local JSON tracker file path.
        tracker (dict): Dictionary of embedded recipe IDs.
    """

    def __init__(self, region="us-east-1", tracker_path="embedded_recipe_ids.json"):
        """
        Initialize AWS clients and load embedding tracker.

        Args:
            region (str): AWS region name.
            tracker_path (str): Path to local embedding tracker file.
        """
        self.s3 = boto3.client("s3", region_name=region)
        self.bedrock = boto3.client("bedrock-runtime", region_name=region)
        self.vector_client = boto3.client("s3vectors", region_name=region)

        self.tracker_path = tracker_path
        self.tracker = self.load_tracker()

    def load_tracker(self):
        """
        Load the recipe embedding tracker file.

        The tracker stores recipe IDs that have already been embedded
        so duplicate embeddings are avoided.

        Returns:
            dict: Dictionary where keys are recipe IDs and values are True.
        """
        if not os.path.exists(self.tracker_path):
            with open(self.tracker_path, "w") as f:
                json.dump({}, f, indent=4)

        with open(self.tracker_path, "r") as f:
            return json.load(f)

    def save_tracker(self):
        """
        Save the current tracker dictionary to disk.
        """
        with open(self.tracker_path, "w") as f:
            json.dump(self.tracker, f, indent=4)

    @staticmethod
    def remove_null_from_dict(d):
        """
        Remove keys with null or empty list values from a dictionary.

        Args:
            d (dict): Dictionary to clean.

        Returns:
            dict: Cleaned dictionary without null or empty list values.
        """
        cleaned_dict = {}

        for key, value in d.items():
            if value is None:
                continue

            if isinstance(value, list) and len(value) == 0:
                continue

            cleaned_dict[key] = value

        return cleaned_dict

    def delete_index_tracker(self, bucket, index):
        """
        Delete the vector index and local tracker file.

        Args:
            bucket (str): Vector bucket name.
            index (str): Vector index name.
        """
        print("Deleting vector index...")

        try:
            self.vector_client.delete_index(
                vectorBucketName=bucket,
                indexName=index
            )

            print("Index deletion initiated. Waiting 30 seconds...")
            time.sleep(30)

        except Exception as e:
            print(f"Index deletion skipped: {e}")

        if os.path.exists(self.tracker_path):
            os.remove(self.tracker_path)
            self.tracker = {}
            print("Tracker cleared.")

    def setup_index_tracker(self, bucket, index):
        """
        Create vector bucket and vector index if they do not exist.

        Args:
            bucket (str): Vector bucket name.
            index (str): Vector index name.
        """
        print(f"Ensuring infrastructure for index: {index}")

        try:
            try:
                self.vector_client.create_vector_bucket(
                    vectorBucketName=bucket
                )
                print("Vector bucket created.")

            except Exception:
                print("Vector bucket already exists.")

            self.vector_client.create_index(
                vectorBucketName=bucket,
                indexName=index,
                dataType="float32",
                dimension=1024,
                distanceMetric="cosine"
            )

            print("Vector index created.")

        except Exception as e:
            if "AlreadyExists" in str(e):
                print("Infrastructure already exists.")
            else:
                print(f"Setup warning: {e}")

    def embed_text(self, text):
        """
        Generate an embedding using Amazon Titan Embed Text v2.

        Args:
            text (str): Input text to embed.

        Returns:
            list[float]: Embedding vector.
        """
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })

        response = self.bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            contentType="application/json",
            accept="application/json",
            body=body
        )

        response_body = json.loads(response["body"].read())

        return response_body["embedding"]

    def embed_recipes(self, bucket, key, vector_bucket, index_name):
        """
        Embed all recipes from a cookbook JSON file.

        Args:
            bucket (str): Source S3 bucket name.
            key (str): S3 object key for cookbook JSON.
            vector_bucket (str): S3 vector bucket name.
            index_name (str): Vector index name.
        """
        obj = self.s3.get_object(Bucket=bucket, Key=key)

        data = json.loads(obj["Body"].read().decode("utf-8"))

        recipes = data.get("recipes", {})
        book_meta = self.remove_null_from_dict(
            data.get("metadata", {})
        )

        book_title = book_meta.get("book_title", "Unknown")

        print(f"Processing: {book_title} ({len(recipes)} recipes)")

        for recipe_id, recipe in recipes.items():

            #if Recipe is already in tracker file, continue
            if recipe_id in self.tracker:
                continue

            recipe_title = recipe.get("recipe_title", "")
            ingredients = recipe.get("recipe_ingredients", [])
            instructions = recipe.get("recipe_instructions", "")

            text = (
                f"Title: {recipe_title}\n"
                f"Book: {book_title}\n"
                f"Ingredients: {', '.join(ingredients)}\n"
                f"Instructions: {instructions}"
            )

            try:
                vector = self.embed_text(text)

                metadata = self.remove_null_from_dict({
                    "recipe_id": recipe_id,
                    "recipe_title": recipe_title,
                    "book_title": book_title,
                    "s3_key": key
                })

                self.vector_client.put_vectors(
                    vectorBucketName=vector_bucket,
                    indexName=index_name,
                    vectors=[{
                        "key": recipe_id,
                        "data": {
                            "float32": vector
                        },
                        "metadata": metadata
                    }]
                )

                self.tracker[recipe_id] = True
                self.save_tracker()

                print(f"Embedded: {recipe_id}")

            except Exception as e:
                print(f"Error embedding {recipe_id}: {e}")


def main():
    """
    Run the recipe embedding pipeline.
    """
    parser = argparse.ArgumentParser(
        description="Recipe Embedding Pipeline"
    )

    parser.add_argument(
        "--src-bucket",
        default="feeding-america-historic-cookbooks",
        help="S3 bucket containing cookbook JSON files"
    )

    parser.add_argument(
        "--vec-bucket",
        default="recipe-vector-bucket",
        help="S3 vector bucket name"
    )

    parser.add_argument(
        "--index",
        default="recipe-index",
        help="Vector index name"
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete vector index and tracker before running"
    )

    args = parser.parse_args()

    pipeline = RecipeEmbedding()

    # Reset infrastructure if requested
    if args.reset:
        pipeline.delete_index_tracker(
            args.vec_bucket,
            args.index
        )

    # Ensure vector infrastructure exists
    pipeline.setup_index_tracker(
        args.vec_bucket,
        args.index
    )

    # Get cookbook files
    response = pipeline.s3.list_objects_v2(
        Bucket=args.src_bucket,
        Prefix="processed_cookbooks/"
    )

    files = [
        obj["Key"]
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".json")
    ]

    print(f"Found {len(files)} cookbook files.")

    # Process each cookbook
    for file_key in files:
        pipeline.embed_recipes(
            args.src_bucket,
            file_key,
            args.vec_bucket,
            args.index
        )


if __name__ == "__main__":
    main()