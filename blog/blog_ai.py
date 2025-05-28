import os
import json
import logging
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Get API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please add it to your .env file.")

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)

class ConversationCache:
    """Manages caching of conversation history for improved context awareness."""
    
    def __init__(self, cache_dir: str = "cache", max_cache_size: int = 100, ttl: int = 86400):
        """
        Initialize the conversation cache.
        
        Args:
            cache_dir: Directory to store conversation cache files
            max_cache_size: Maximum number of conversations to cache
            ttl: Time-to-live for cache entries in seconds (default: 24 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.max_cache_size = max_cache_size
        self.ttl = ttl
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.template_info = self._load_template_information()
        self._load_cache()
    
    def _load_template_information(self) -> Dict[str, Any]:
        """Load template information from the template_context.json file and templates.txt."""
        try:
            template_file = self.cache_dir / "template_context.json"
            templates_data = {"templates": []}
            
            if template_file.exists():
                with open(template_file, 'r') as f:
                    templates_data = json.load(f)
            else:
                logger.warning(f"Template context file not found: {template_file}")
            
            # Also load raw template data from templates.txt
            templates_txt_path = Path("blog/templates.txt")
            raw_templates_content = ""
            if templates_txt_path.exists():
                # Try different encodings to handle potential issues
                encodings_to_try = ['utf-8', 'latin-1', 'utf-16', 'cp1252']
                for encoding in encodings_to_try:
                    try:
                        with open(templates_txt_path, 'r', encoding=encoding) as f:
                            raw_templates_content = f.read()
                        logger.info(f"Loaded templates.txt content using {encoding} encoding ({len(raw_templates_content)} bytes)")
                        break
                    except UnicodeDecodeError as e:
                        logger.warning(f"Failed to read templates.txt with {encoding} encoding: {e}")
                    except Exception as e:
                        logger.error(f"Error reading templates.txt with {encoding} encoding: {e}")
                        
                if not raw_templates_content:
                    logger.error("Failed to read templates.txt with all attempted encodings")
            else:
                logger.warning(f"Templates.txt file not found: {templates_txt_path}")
            
            # Add raw templates content to the returned data
            templates_data["raw_templates"] = raw_templates_content
            return templates_data
        except Exception as e:
            logger.error(f"Error loading template information: {e}")
            return {"templates": [], "raw_templates": ""}
    
    def _load_cache(self) -> None:
        """Load existing cache from disk."""
        try:
            for file_path in self.cache_dir.glob("*.json"):
                # Skip the template context file
                if file_path.name == "template_context.json":
                    continue
                    
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        if self._is_valid_cache_entry(data):
                            self.cache[data["conversation_id"]] = data
                except Exception as e:
                    logger.error(f"Error loading cache file {file_path}: {e}")
            
            # Clean up expired or excess cache entries
            self._clean_cache()
            logger.info(f"Loaded {len(self.cache)} conversation contexts from cache")
        except Exception as e:
            logger.error(f"Error initializing cache: {e}")
    
    def _is_valid_cache_entry(self, data: Dict[str, Any]) -> bool:
        """Check if a cache entry is valid and not expired."""
        required_keys = ["conversation_id", "timestamp", "history"]
        if not all(key in data for key in required_keys):
            return False
        
        # Check if entry has expired
        timestamp = data.get("timestamp", 0)
        current_time = time.time()
        return (current_time - timestamp) <= self.ttl
    
    def _clean_cache(self) -> None:
        """Remove expired entries and limit cache size."""
        current_time = time.time()
        
        # Remove expired entries
        expired_ids = [
            conv_id for conv_id, data in self.cache.items()
            if (current_time - data.get("timestamp", 0)) > self.ttl
        ]
        for conv_id in expired_ids:
            self._remove_from_cache(conv_id)
        
        # Limit cache size if needed
        if len(self.cache) > self.max_cache_size:
            # Sort by timestamp (oldest first)
            sorted_entries = sorted(
                self.cache.items(),
                key=lambda item: item[1].get("timestamp", 0)
            )
            # Remove oldest entries to maintain max size
            for conv_id, _ in sorted_entries[:len(self.cache) - self.max_cache_size]:
                self._remove_from_cache(conv_id)
    
    def _remove_from_cache(self, conversation_id: str) -> None:
        """Remove a conversation from cache and delete its file."""
        if conversation_id in self.cache:
            del self.cache[conversation_id]
            
            # Remove the cache file
            cache_file = self.cache_dir / f"{conversation_id}.json"
            if cache_file.exists():
                cache_file.unlink()
    
    def get_conversation(self, conversation_id: str) -> List[Dict[str, str]]:
        """Get conversation history for a given ID."""
        if conversation_id in self.cache:
            data = self.cache[conversation_id]
            # Update timestamp to prevent expiration of active conversations
            data["timestamp"] = time.time()
            self._save_conversation(conversation_id, data["history"])
            return data["history"]
        return []
    
    def update_conversation(self, conversation_id: str, history: List[Dict[str, str]]) -> None:
        """Update or create a conversation in the cache."""
        self.cache[conversation_id] = {
            "conversation_id": conversation_id,
            "timestamp": time.time(),
            "history": history
        }
        self._save_conversation(conversation_id, history)
        self._clean_cache()
    
    def _save_conversation(self, conversation_id: str, history: List[Dict[str, str]]) -> None:
        """Save conversation to disk."""
        try:
            cache_file = self.cache_dir / f"{conversation_id}.json"
            with open(cache_file, 'w') as f:
                json.dump({
                    "conversation_id": conversation_id,
                    "timestamp": time.time(),
                    "history": history
                }, f)
        except Exception as e:
            logger.error(f"Error saving conversation to cache: {e}")
    
    def clear_conversation(self, conversation_id: str) -> None:
        """Clear a specific conversation from cache."""
        self._remove_from_cache(conversation_id)
    
    def clear_all(self) -> None:
        """Clear all conversations from cache."""
        for conv_id in list(self.cache.keys()):
            self._remove_from_cache(conv_id)
    
    def add_template_context_to_conversation(self, conversation_id: str) -> None:
        """Add template information to a conversation as context."""
        if not self.template_info or "templates" not in self.template_info:
            logger.warning("No template information available to add to conversation")
            return
            
        # Format template information into a clear message
        template_details = []
        for template in self.template_info.get("templates", []):
            template_info = (
                f"Template {template.get('id')}: {template.get('name')}\n"
                f"Key: {template.get('template_key')}\n"
                f"Purpose: {template.get('purpose')}\n"
                f"Best Used For: {', '.join(template.get('best_used_for', []))}\n"
                f"Structure: {', '.join(template.get('structure', []))}\n"
                f"Example Topics: {', '.join(template.get('example_topics', []))}\n"
            )
            template_details.append(template_info)
        
        # Check if we have raw templates content to include
        raw_templates = self.template_info.get("raw_templates", "")
        template_selection_guidance = ""
        if raw_templates:
            template_selection_guidance = (
                "\n\nTEMPLATE SELECTION GUIDELINES:\n"
                "Use the following detailed template descriptions to determine which template is most appropriate for a given topic.\n"
                "These descriptions contain the full intent and structure of each template type:\n\n"
                f"{raw_templates}\n\n"
                "IMPORTANT: Use these detailed template descriptions to guide your decision, but refer to templates using the IDs and keys from the template information above."
            )
            
        template_context = (
            "TEMPLATE INFORMATION:\n\n" +
            "\n\n".join(template_details) +
            template_selection_guidance +
            "\n\nIMPORTANT: When selecting a template, use the structured template information above in conjunction with the detailed template descriptions to decide which template (by template ID and name) would be most appropriate for the given topic."
        )
        
        # Get existing conversation
        history = self.get_conversation(conversation_id)
        
        # Check if template context is already in the conversation
        template_already_added = any(
            message.get("role") == "system" and "TEMPLATE INFORMATION" in message.get("content", "")
            for message in history
        )
        
        if not template_already_added:
            # Add template context as a system message
            system_message = {"role": "system", "content": template_context}
            
            # If there's an existing system message, add it after that
            system_index = next((i for i, msg in enumerate(history) 
                                if msg.get("role") == "system"), -1)
            
            if system_index >= 0:
                history.insert(system_index + 1, system_message)
            else:
                history.insert(0, system_message)
                
            # Update the conversation in cache
            self.update_conversation(conversation_id, history)
            logger.info(f"Added template context to conversation {conversation_id}")

    def get_preferred_template(self, topic_keyword: str) -> Dict[str, Any]:
        """
        Determine the preferred template to use for a given topic based on templates.txt and context_cache.json.
        
        Args:
            topic_keyword: The topic keyword to analyze
            
        Returns:
            Dict containing the preferred template information
        """
        try:
            # Default template if we can't determine a better one
            default_template = {
                "id": 5,
                "template_key": "template5",
                "name": "How-To Guide SEO Blog Template (Step-by-Step Evergreen)",
                "template_type": "how_to"
            }
            
            # If we don't have template information, return the default
            if not self.template_info or "templates" not in self.template_info:
                logger.warning("No template information available to determine preferred template")
                return default_template
                
            # Get structured templates from context_cache.json
            templates = self.template_info.get("templates", [])
            if not templates:
                logger.warning("No templates found in context cache")
                return default_template
                
            # Get raw templates content from templates.txt
            raw_templates = self.template_info.get("raw_templates", "")
            if not raw_templates:
                logger.warning("No raw templates content found")
                
            # Simple keyword-based matching as a fallback
            # This is a basic implementation - in production, you might want to use
            # more sophisticated NLP techniques or AI to determine the best template
            
            # Check if the topic contains comparison keywords
            comparison_keywords = ["vs", "versus", "comparison", "compare", "better", "best"]
            if any(keyword in topic_keyword.lower() for keyword in comparison_keywords):
                # Match to Comparison Blog Structure (template3)
                for template in templates:
                    if template.get("id") == 3:
                        return {
                            "id": template.get("id"),
                            "template_key": template.get("template_key"),
                            "name": template.get("name"),
                            "template_type": "review"
                        }
            
            # Check if topic contains news/trending keywords
            news_keywords = ["news", "update", "latest", "trend", "announced", "release"]
            if any(keyword in topic_keyword.lower() for keyword in news_keywords):
                # Match to Trend-Based SEO Blog Structure (template2)
                for template in templates:
                    if template.get("id") == 2:
                        return {
                            "id": template.get("id"),
                            "template_key": template.get("template_key"),
                            "name": template.get("name"),
                            "template_type": "news"
                        }
            
            # Check if topic contains location-based keywords
            location_keywords = ["in", "near", "city", "region", "area", "local"]
            location_pattern = r'\b(in|near|at)\s+[A-Z][a-z]+'  # Simple regex for "in City" pattern
            if any(keyword in topic_keyword.lower() for keyword in location_keywords) or re.search(location_pattern, topic_keyword):
                # Match to Local SEO Blog Template (template4)
                for template in templates:
                    if template.get("id") == 4:
                        return {
                            "id": template.get("id"),
                            "template_key": template.get("template_key"),
                            "name": template.get("name"),
                            "template_type": "opinion"
                        }
            
            # Check if topic contains how-to keywords
            howto_keywords = ["how to", "steps", "guide", "tutorial", "diy", "process"]
            if any(keyword in topic_keyword.lower() for keyword in howto_keywords):
                # Match to How-To Guide SEO Blog Template (template5)
                for template in templates:
                    if template.get("id") == 5:
                        return {
                            "id": template.get("id"),
                            "template_key": template.get("template_key"),
                            "name": template.get("name"),
                            "template_type": "how_to"
                        }
            
            # Default to Evergreen Pillar Page Structure for broad topics
            for template in templates:
                if template.get("id") == 1:
                    return {
                        "id": template.get("id"),
                        "template_key": template.get("template_key"),
                        "name": template.get("name"),
                        "template_type": "how_to"
                    }
            
            # If no specific template was found, return default
            return default_template
            
        except Exception as e:
            logger.error(f"Error determining preferred template: {e}")
            return default_template

class GeminiChatbot:
    """Advanced chatbot using Google's Gemini API with context caching."""
    
    def __init__(
        self, 
        model_name: str = "gemini-1.5-pro", 
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        top_p: float = 0.95,
        top_k: int = 40,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize the Gemini chatbot.
        
        Args:
            model_name: Gemini model name to use
            temperature: Sampling temperature (higher = more creative, lower = more focused)
            max_output_tokens: Maximum number of tokens to generate
            top_p: Nucleus sampling probability threshold
            top_k: Number of highest probability tokens to consider
            system_prompt: Optional system prompt to define chatbot behavior
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.top_p = top_p
        self.top_k = top_k
        
        # Initialize the model
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "top_p": top_p,
                "top_k": top_k,
            },
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
        )
        
        # Create conversation cache
        self.cache = ConversationCache()
        
        # Set system prompt
        self.system_prompt = system_prompt or (
            "You are a helpful, friendly, and knowledgeable AI assistant for a blog platform. "
            "Provide concise, accurate, and helpful responses to users' questions. "
            "Always be respectful and professional. If you don't know the answer, "
            "be honest about it rather than making up information."
        )
    
    def chat(self, user_input: str, conversation_id: str = None, context: Optional[List[Dict[str, str]]] = None, include_template_info: bool = False) -> Dict[str, Any]:
        """
        Process a user input and generate a response.
        
        Args:
            user_input: User's message
            conversation_id: Unique identifier for the conversation
            context: Optional context to override cached conversation history
            include_template_info: Whether to include template information in the context
            
        Returns:
            Dict containing response text and metadata
        """
        start_time = time.time()
        
        # Generate conversation ID if not provided
        if not conversation_id:
            conversation_id = f"conv_{int(time.time())}_{hash(user_input) % 10000}"
        
        # Get conversation history from cache or use provided context
        history = context or self.cache.get_conversation(conversation_id)
        
        # Add template information to the conversation if requested
        if include_template_info:
            self.cache.add_template_context_to_conversation(conversation_id)
            # Refresh history to include the template information
            history = self.cache.get_conversation(conversation_id)
        
        try:
            # Create chat session
            chat = self.model.start_chat(history=self._format_history_for_gemini(history))
            
            # Add system prompt if this is a new conversation
            if not history:
                logger.info(f"Starting new conversation: {conversation_id}")
                # The system prompt is set through the first message in this implementation
                system_message = {"role": "system", "content": self.system_prompt}
                history.append(system_message)
            
            # Add user input to history
            user_message = {"role": "user", "content": user_input}
            history.append(user_message)
            
            # Generate response
            response = chat.send_message(user_input)
            response_text = response.text
            
            # Add model's response to history
            model_message = {"role": "assistant", "content": response_text}
            history.append(model_message)
            
            # Update cache with new conversation history
            self.cache.update_conversation(conversation_id, history)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            return {
                "response": response_text,
                "conversation_id": conversation_id,
                "model": self.model_name,
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error in chat processing: {e}")
            return {
                "response": "I'm sorry, I encountered an error processing your request.",
                "conversation_id": conversation_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def _format_history_for_gemini(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Convert internal history format to Gemini API format."""
        gemini_history = []
        for message in history:
            role = message.get("role", "")
            content = message.get("content", "")
            
            # Skip system messages as they're handled differently
            if role == "system":
                continue
            
            # Map roles to Gemini format
            if role == "user":
                gemini_history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})
        
        return gemini_history
    
    def clear_conversation(self, conversation_id: str) -> None:
        """Clear a specific conversation from cache."""
        self.cache.clear_conversation(conversation_id)
    
    def clear_all_conversations(self) -> None:
        """Clear all conversations from cache."""
        self.cache.clear_all()
    
    def get_conversation_history(self, conversation_id: str) -> List[Dict[str, str]]:
        """Retrieve the full conversation history."""
        return self.cache.get_conversation(conversation_id)

class GeminiTrainer:
    """Training and evaluation utilities for the Gemini chatbot."""
    
    def __init__(self, chatbot: GeminiChatbot):
        """
        Initialize the trainer with a GeminiChatbot instance.
        
        Args:
            chatbot: An instance of GeminiChatbot
        """
        self.chatbot = chatbot
        self.evaluation_results = []
    
    def evaluate_on_dataset(self, test_data: List[Dict[str, Any]], verbose: bool = True) -> Dict[str, Any]:
        """
        Evaluate the chatbot on a test dataset.
        
        Args:
            test_data: List of test examples, each with "query" and "expected" fields
            verbose: Whether to print evaluation progress
            
        Returns:
            Dictionary with evaluation metrics
        """
        results = {
            "total_examples": len(test_data),
            "successful": 0,
            "failed": 0,
            "details": [],
            "avg_response_time": 0,
        }
        
        total_time = 0
        
        for i, example in enumerate(test_data):
            query = example.get("query", "")
            expected = example.get("expected", "")
            context = example.get("context", [])
            
            if verbose:
                logger.info(f"Evaluating example {i+1}/{len(test_data)}")
            
            # Generate response
            conversation_id = f"test_{i}_{int(time.time())}"
            response_data = self.chatbot.chat(query, conversation_id, context)
            
            # Extract metrics
            response_text = response_data.get("response", "")
            processing_time = response_data.get("processing_time", 0)
            total_time += processing_time
            
            # Simple exact match evaluation (can be replaced with more sophisticated metrics)
            success = expected.lower() in response_text.lower()
            
            # Store result
            detail = {
                "query": query,
                "response": response_text,
                "expected": expected,
                "success": success,
                "processing_time": processing_time,
            }
            
            results["details"].append(detail)
            if success:
                results["successful"] += 1
            else:
                results["failed"] += 1
        
        # Calculate average response time
        if results["total_examples"] > 0:
            results["avg_response_time"] = total_time / results["total_examples"]
        
        # Calculate success rate
        results["success_rate"] = results["successful"] / results["total_examples"] if results["total_examples"] > 0 else 0
        
        self.evaluation_results.append({
            "timestamp": datetime.now().isoformat(),
            "model": self.chatbot.model_name,
            "results": results
        })
        
        return results
    
    def save_evaluation_results(self, filename: str = "evaluation_results.json") -> None:
        """Save evaluation results to a JSON file."""
        try:
            with open(filename, 'w') as f:
                json.dump(self.evaluation_results, f, indent=2)
            logger.info(f"Evaluation results saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving evaluation results: {e}")
    
    def load_test_dataset(self, filename: str) -> List[Dict[str, Any]]:
        """Load test dataset from a JSON file."""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded test dataset with {len(data)} examples from {filename}")
            return data
        except Exception as e:
            logger.error(f"Error loading test dataset: {e}")
            return []
    
    def create_test_dataset(self, queries: List[str], expected_responses: List[str], 
                           contexts: Optional[List[List[Dict[str, str]]]] = None) -> List[Dict[str, Any]]:
        """Create a test dataset from queries and expected responses."""
        dataset = []
        
        for i, (query, expected) in enumerate(zip(queries, expected_responses)):
            example = {
                "query": query,
                "expected": expected
            }
            
            if contexts and i < len(contexts):
                example["context"] = contexts[i]
            
            dataset.append(example)
        
        return dataset

def sample_usage():
    """Sample usage of the Gemini chatbot and trainer."""
    
    # Initialize chatbot
    chatbot = GeminiChatbot(
        model_name="gemini-1.5-pro",
        temperature=0.7,
        system_prompt="You are a helpful AI assistant for a blog platform."
    )
    
    # Chat example
    conversation_id = "sample_conversation"
    response = chatbot.chat("Hello, can you help me write a blog post about AI?", conversation_id)
    print(f"Response: {response['response']}")
    
    # Continue conversation
    response = chatbot.chat("What topics should I cover?", conversation_id)
    print(f"Response: {response['response']}")
    
    # Template selection example with template context
    template_conv_id = "template_selection_example"
    template_query = "I need to select the best template for a blog post comparing iPhone and Android phones. Which template would be most appropriate?"
    
    # Include template information in the context
    response = chatbot.chat(template_query, template_conv_id, include_template_info=True)
    print(f"Template Selection Response: {response['response']}")
    
    # Training and evaluation example
    trainer = GeminiTrainer(chatbot)
    
    # Create a small test dataset
    test_data = trainer.create_test_dataset(
        queries=["What is machine learning?", "Explain neural networks briefly"],
        expected_responses=["Machine learning", "neural networks"]
    )
    
    # Evaluate
    results = trainer.evaluate_on_dataset(test_data)
    print(f"Evaluation results: {results['success_rate']*100:.2f}% success rate")
    
    # Save results
    trainer.save_evaluation_results()

if __name__ == "__main__":
    # This will only run when the script is executed directly
    # Uncomment to see sample usage
    # sample_usage()
    
    # Simple interactive mode
    print("Gemini Chatbot initialized. Type 'exit' to quit.")
    chatbot = GeminiChatbot()
    conversation_id = f"interactive_{int(time.time())}"
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['exit', 'quit', 'bye']:
            break
            
        response = chatbot.chat(user_input, conversation_id)
        print(f"\nChatbot: {response['response']}")
