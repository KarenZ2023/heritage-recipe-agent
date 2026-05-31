#!/usr/bin/env python3
"""
Parse recipes from cookbooks and store each cookbook into a json file.
"""

import os
import xml.etree.ElementTree as ET
import string
import json
import boto3
import argparse
import botocore

class RecipeParser:
    """Parses XML recipe elements into structured dictionaries.

    Attributes:
        recipe (xml.etree.ElementTree.Element): The XML element containing recipe data.
        recipe_id (str): Unique identifier for the recipe.
        recipe_dict (dict): Dictionary to store parsed recipe details.
    """

    def __init__(self, recipe, recipe_id):
        """Initializes the parser with a recipe element and a numeric ID.

        Args:
            recipe (xml.etree.ElementTree.Element): The recipe XML element to parse.
            recipe_id (str): The numeric ID to assign to this recipe.
        """
        self.recipe = recipe
        self.recipe_id = recipe_id
        self.recipe_dict = {}

    def get_recipe_title(self):
        """Extracts and cleans the recipe title from the XML.

        Returns:
            str: The cleaned recipe title, or None if not found.
        """
        purpose = self.recipe.find('p/purpose')
        if purpose is None:
            return None

        title = "".join(purpose.itertext()).strip()
        return title.rstrip('.')

    def get_ingredients(self):
        """Returns a list of unique, cleaned ingredients for the recipe.

        Returns:
            list: A list of unique ingredients.
        """
        ingredients = self.recipe.findall(".//ingredient")
        cleaned_ingredients = []

        for i in ingredients:
            if i.text:
                text = i.text.lower().strip(string.punctuation)
                cleaned_ingredients.append(text)

        return list(dict.fromkeys(cleaned_ingredients))

    def get_cooking_instructions(self):
        """Extracts and formats the cooking instructions text.

        Returns:
            str: A single string of normalized text instructions.
        """
        instructions = "".join(self.recipe.itertext()).strip()
        return ' '.join(instructions.split())

    def get_recipe_category(self):
        """Retrieves the recipe category from XML attributes.

        Returns:
            str: The category name or None if unavailable.
        """
        return self.recipe.attrib.get('class1')

    def recipe_to_dict(self):
        """Converts the XML recipe into a dictionary.

        The recipe must have least 2 ingredients, 30 characters of instructions, 
        and a valid title.

        Returns:
            dict: The recipe data if valid, otherwise None.
        """
        ingredients = self.get_ingredients()
        instructions = self.get_cooking_instructions()
        title = self.get_recipe_title()
        category = self.get_recipe_category()

        if (ingredients and len(ingredients) >= 2) and \
           (instructions and len(instructions) >= 30) and title:
            
            self.recipe_dict = {
                'recipe_id': self.recipe_id,
                'recipe_title': title,
                'recipe_category': category,
                'recipe_ingredients': ingredients,
                'recipe_instructions': instructions
            }
            return self.recipe_dict

        return None

class BookParser:
    """Parses an entire XML recipe book into a nested dictionary structure.

    Attributes:
        root (xml.etree.ElementTree.Element): The root element of the XML book.
        book_dict (dict): Dictionary containing all parsed book data, including its book attributes and recipes
    """

    def __init__(self, book_xml):
        """Initializes the parser with book XML content.

        Args:
            book_xml (bytes/str): The raw XML content of the cookbook.
        """
        self.root = ET.fromstring(book_xml)
        self.book_dict = {}

    def get_book_attr(self):
        """Extracts top-level book attributes.

        Returns:
            dict: Values can include book ID, region, and historical period.
        """
        attribs = self.root.attrib
        return {
            'book_id': attribs.get('bookID'),
            'book_type': attribs.get('type'),
            'book_class': attribs.get('class1'),
            'book_region': attribs.get('region'),
            'book_ethnic_group': attribs.get('ethnicgroup'),
            'book_historic_period': attribs.get('histperiod')
        }

    def get_meta_attr(self):
        """Extracts metadata from the 'meta' XML tag.

        Returns:
            dict: Values can include book title, author, and published year.
        """
        meta_attr = {}
        meta_element = self.root.find('meta')

        if meta_element is not None:
            meta_attr['book_title'] = self.root.findtext('meta/dcTitle')
            meta_attr['book_creator'] = self.root.findtext('meta/dcCreator')
            meta_attr['book_description'] = self.root.findtext('meta/dcDescription')
            meta_attr['book_publisher'] = self.root.findtext('meta/dcPublisher')
            meta_attr['book_year'] = self.root.findtext('meta/dcDate')

        return meta_attr

    def book_to_dict(self, recipe_limit=None):
        """Orchestrates the parsing of metadata and all contained recipes.

        Args:
            recipe_limit (int, optional): Max number of recipes to parse per book.

        Returns:
            dict: Complete dictionary of the book's attributes, metadata, and recipes.
        """
        book_attr = self.get_book_attr()

        self.book_dict = {
            'attributes': book_attr,
            'metadata': self.get_meta_attr(),
            'recipes': {}
        }

        recipe_elements = self.root.findall(".//recipe")
        recipe_count = 0

        for recipe_obj in recipe_elements:
            recipe_count += 1
            if recipe_limit is not None and recipe_count > recipe_limit:
                break

            recipe_id = f"{book_attr['book_id']}_{recipe_count}"
            parser = RecipeParser(recipe_obj, recipe_id)
            recipe_dict = parser.recipe_to_dict()

            if recipe_dict is not None:
                self.book_dict['recipes'][recipe_id] = recipe_dict

        self.book_dict['recipe_num'] = len(self.book_dict['recipes'])
        return self.book_dict

def main():
    """Main execution block to process cookbooks from S3 bucket."""
    
    parser = argparse.ArgumentParser(description="Parse cookbooks from S3.")
    parser.add_argument("--book_limit", type=int, default=0, help="Number of books to process")
    parser.add_argument("--bucket", type=str, default="feeding-america-historic-cookbooks")
    parser.add_argument("--input_folder", type=str, default="cookbook_textencoded", help="S3 folder name for cookbook XMLs")
    parser.add_argument("--output_folder", type=str, default="processed_cookbooks", help="S3 folder name for cookbook output JSONs")
    args = parser.parse_args()

    input_prefix = args.input_folder  + '/'
    output_prefix = args.output_folder  + '/'

    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=args.bucket, Prefix=input_prefix)

    #read contents of the input XML folder
    book_count = 0
    for page in pages:
        if 'Contents' not in page:
            continue
    
        for obj in page['Contents']:
            source_key = obj['Key']
    
            # Skip the folder itself
            if source_key == input_prefix:
                continue
    
            file_name = os.path.basename(source_key)
            if not file_name.lower().endswith('.xml'):
                continue
    
            
            print(f"Processing: {source_key}")
            book_name = os.path.splitext(file_name)[0]

            try:
                # 1. Check if the JSON file already exists
                json_key = f'{output_prefix}{book_name}.json'
                
                try:
                    s3.head_object(Bucket=args.bucket, Key=json_key)
                    print(f"  - '{json_key}' has already been parsed. Skipping.")
                    continue  # Safely skips to next book without affecting your limit count!
                    
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] != "404":
                        raise  
            
                # This ensures we only count books we are ACTUALLY processing right now
                book_count += 1
                if args.book_limit > 0 and book_count > args.book_limit:
                    print(f"Reached limit of {args.book_limit} newly processed books. Exiting.")
                    return 

                # 2. Download and parse the XML
                response = s3.get_object(Bucket=args.bucket, Key=source_key)
                book_xml = response["Body"].read()
                
                parser = BookParser(book_xml)
                book_dict = parser.book_to_dict()
            
                # 3. Check recipe count
                if book_dict.get("recipe_num", 0) == 0:
                    print(f'  - No valid recipes found. Skipping JSON creation.\n')
                else:
                    # 4. Upload to S3
                    json_content = json.dumps(book_dict, indent=4, ensure_ascii=False)
            
                    s3.put_object(
                        Bucket=args.bucket,
                        Key=json_key,
                        Body=json_content,
                        ContentType='application/json'
                    )
                    print(f'  - Successfully saved {book_dict["recipe_num"]} recipes to {json_key}\n')
            
            except Exception as e:
                print(f"Error processing {source_key}: {e}")
if __name__ == "__main__":
    main()