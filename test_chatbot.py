#!/usr/bin/env python
"""Test script for the Gemini chatbot."""
import json
import os
from blog.blog_ai import GeminiChatbot, GeminiTrainer

def main():
    """Run basic tests for the Gemini chatbot."""
    print("=== Gemini Chatbot Testing ===")
    
    # Check if API key is available
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️ Warning: GEMINI_API_KEY not found in environment variables.")
        print("Please add it to your .env file or set it as an environment variable.")
        return
        
    # Initialize the chatbot
    print("\n1. Initializing chatbot...")
    chatbot = GeminiChatbot(
        temperature=0.5,  # Lower temperature for more focused responses
        system_prompt="You are a specialized blog writing assistant. You help users write, improve, and optimize blog content."
    )
    
    # Test basic chat functionality
    print("\n2. Testing basic chat...")
    conversation_id = "test_conversation"
    
    queries = [
        "What are the key elements of a successful blog post?",
        "How long should a blog post be for optimal SEO?",
        "What's a good structure for a technical tutorial?",
    ]
    
    # Run a short conversation
    for query in queries:
        print(f"\nUser: {query}")
        response = chatbot.chat(query, conversation_id)
        print(f"Chatbot: {response['response'][:200]}...")  # Show first 200 chars
        print(f"Processing time: {response['processing_time']:.2f}s")
    
    # Test context awareness
    print("\n3. Testing context awareness...")
    contextual_query = "Can you elaborate on the previous point about structure?"
    print(f"\nUser: {contextual_query}")
    response = chatbot.chat(contextual_query, conversation_id)
    print(f"Chatbot: {response['response'][:200]}...")
    
    # Retrieve and display conversation history
    print("\n4. Retrieving conversation history...")
    history = chatbot.get_conversation_history(conversation_id)
    print(f"Conversation has {len(history)} messages")
    
    # Create and save a simple test dataset
    print("\n5. Creating test dataset...")
    trainer = GeminiTrainer(chatbot)
    test_data = trainer.create_test_dataset(
        queries=[
            "What is a blog?",
            "How do I increase my blog traffic?"
        ],
        expected_responses=[
            "A blog is",
            "traffic"
        ]
    )
    
    # Save test dataset to file
    with open("test_dataset.json", "w") as f:
        json.dump(test_data, f, indent=2)
    print(f"Created test dataset with {len(test_data)} examples")
    
    # Run a brief evaluation
    print("\n6. Running evaluation...")
    results = trainer.evaluate_on_dataset(test_data)
    print(f"Success rate: {results['success_rate']*100:.2f}%")
    print(f"Average response time: {results['avg_response_time']:.2f}s")
    
    # Save evaluation results
    trainer.save_evaluation_results("test_results.json")
    print("Evaluation results saved to test_results.json")
    
    print("\n=== Testing complete ===")

if __name__ == "__main__":
    main() 