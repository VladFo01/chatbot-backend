import asyncio
import logging
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.prompts import ChatPromptTemplate
from app.config import get_settings
from app.services.document_processor import document_processor

logger = logging.getLogger(__name__)
settings = get_settings()

class LLMService:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI API key not provided. LLM functionality will be limited.")
            self.llm = None
        else:
            self.llm = ChatOpenAI(
                openai_api_key=settings.OPENAI_API_KEY,
                model_name="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=1000
            )
        
        self.system_prompt = """You are a helpful AI assistant. Answer questions directly and naturally without referencing sources or context.

CRITICAL INSTRUCTIONS:
- NEVER start responses with "Based on the provided context" or similar phrases
- NEVER mention "sources", "documents", or "context" in your response
- NEVER include filenames or document references
- Answer questions directly as if the information is your own knowledge
- Be helpful, concise, and informative
- If you don't know something, just say "I don't have information about that"

Context from documents:
{context}

Answer the user's question naturally without mentioning this context."""

    async def generate_response(
        self, 
        message: str, 
        chat_history: List[Dict[str, Any]] = None,
        use_rag: bool = True,
        k_documents: int = 5
    ) -> Dict[str, Any]:
        """Generate LLM response with optional RAG (Retrieval Augmented Generation)"""
        try:
            context = ""
            sources = []
            
            if use_rag:
                # Search for relevant documents
                search_results = await document_processor.search_similar_documents(message, k_documents)
                
                if search_results:
                    context_parts = []
                    logger.info(f"Found {len(search_results)} relevant documents for query: '{message[:100]}...'")
                    
                    for i, result in enumerate(search_results):
                        context_parts.append(
                            f"Source {i+1} (from {result['metadata']['filename']}):\n{result['content']}\n"
                        )
                        sources.append({
                            "filename": result['metadata']['filename'],
                            "file_id": result['metadata']['file_id'],
                            "similarity_score": result['similarity_score'],
                            "content_preview": result['content'][:200] + "..." if len(result['content']) > 200 else result['content']
                        })
                        
                        # Log each source with similarity score and content preview
                        logger.info(f"  Source {i+1}: {result['metadata']['filename']} "
                                   f"(similarity: {result['similarity_score']:.3f}) - "
                                   f"Content preview: {result['content'][:150]}...")
                    
                    context = "\n".join(context_parts)
                    logger.info(f"Total context length: {len(context)} characters")
                else:
                    logger.info(f"No relevant documents found for query: '{message[:100]}...'")
            else:
                logger.info(f"RAG disabled for query: '{message[:100]}...')")
                
            # Prepare messages for the LLM
            messages = []
            
            # Add system message with context
            system_content = self.system_prompt.format(context=context if context else "No relevant context found.")
            messages.append(SystemMessage(content=system_content))
            
            # Log the context being sent to LLM
            if context:
                logger.info(f"Sending context to LLM (length: {len(context)} chars):")
                logger.debug(f"Context content:\n{context[:500]}...")
            else:
                logger.info("No context sent to LLM - using general knowledge")
            
            # Add chat history if provided
            if chat_history:
                for msg in chat_history[-10:]:  # Last 10 messages for context
                    if msg.get("sender") == "user":
                        messages.append(HumanMessage(content=msg.get("message", "")))
                    elif msg.get("sender") == "assistant":
                        messages.append(AIMessage(content=msg.get("message", "")))
            
            # Add current user message
            messages.append(HumanMessage(content=message))
            
            # Generate response
            response = await self._generate_async(messages)
            
            # Log the response details
            context_used = bool(context)
            logger.info(f"LLM Response generated - Context used: {context_used}, "
                       f"Sources: {len(sources)}, Response length: {len(response.content)} chars")
            logger.debug(f"LLM Response content: {response.content[:200]}...")
            
            return {
                "response": response.content,
                "sources": sources,
                "context_used": context_used,
                "model": "gpt-3.5-turbo"
            }
            
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            
            # If OpenAI is not configured, provide a helpful response with context
            if "OpenAI API key not configured" in str(e) and context:
                return {
                    "response": f"I found relevant information in your documents but cannot generate a full response without OpenAI API configuration. Here's what I found:\n\n{context[:500]}...",
                    "sources": sources,
                    "context_used": True,
                    "error": "OpenAI API key not configured"
                }
            
            return {
                "response": "I apologize, but I encountered an error while generating a response. Please try again.",
                "sources": [],
                "context_used": False,
                "error": str(e)
            }

    async def _generate_async(self, messages):
        """Generate response asynchronously"""
        if not self.llm:
            raise ValueError("OpenAI API key not configured. Cannot generate responses.")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.llm, messages)
        return response

    async def generate_summary(self, text: str, max_length: int = 200) -> str:
        """Generate a summary of the provided text"""
        try:
            prompt = f"""Please provide a concise summary of the following text in no more than {max_length} words:

{text}

Summary:"""
            
            messages = [HumanMessage(content=prompt)]
            response = await self._generate_async(messages)
            return response.content
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Unable to generate summary."

    async def generate_questions(self, text: str, num_questions: int = 3) -> List[str]:
        """Generate relevant questions based on the document content"""
        try:
            prompt = f"""Based on the following text, generate {num_questions} relevant questions that someone might ask about this content:

{text}

Questions:"""
            
            messages = [HumanMessage(content=prompt)]
            response = await self._generate_async(messages)
            
            # Parse questions from response
            questions = []
            for line in response.content.split('\n'):
                line = line.strip()
                if line and (line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or 
                           line.startswith('-') or line.startswith('•')):
                    # Clean up the question
                    question = line.lstrip('123.-•').strip()
                    if question:
                        questions.append(question)
            
            return questions[:num_questions]
            
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            return []

# Global instance
llm_service = LLMService() 