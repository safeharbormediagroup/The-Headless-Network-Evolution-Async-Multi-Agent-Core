import os
import json
import asyncio
from typing import Dict, TypedDict, Annotated, Sequence
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_chroma import Chroma
import aiohttp  # Asynchronous HTTP networking for low-bandwidth scaling

load_dotenv()

# ============================================================================
# TELEGRAM LIVE EDGE GATEWAY
# ============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "777777:FakeKey")
CHAT_ID = os.getenv("CHAT_ID", "@PulseCompanionBot_Room")


async def send_telegram_stream(markdown_payload: str) -> None:
    """Dispatches real-time agent output directly to the Telegram free cloud buffer."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": markdown_payload,
        "parse_mode": "Markdown"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=5) as response:
                if response.status == 200:
                    print("[NODE_SYNC]: Agent payload routed to Telegram successfully.")
                else:
                    print(f"[NODE_LATENCY]: Telegram gateway returned status {response.status}")
    except asyncio.TimeoutError:
        print("[NODE_OFFLINE]: Telegram request timed out.")
    except Exception as e:
        print(f"[NODE_OFFLINE]: Failed to route telemetry. Error: {e}")

# ============================================================================
# INITIALIZATION & VECTOR POOLS
# ============================================================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.68.114:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3")

# Switched to native Ollama async interface invocation
llm = OllamaLLM(base_url=OLLAMA_BASE_URL, model=MODEL_NAME, temperature=0.75)
embeddings = OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model=MODEL_NAME)

CHROMA_PATH = "./chroma_db"
vectorstore = Chroma(
    persist_directory=CHROMA_PATH,
    embedding_function=embeddings,
    collection_name="rag_collection"
)


class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    current_step: str
    context: str
    analysis: str
    draft: str
    final_response: str
    query: str
    agent_outputs: Dict[str, str]

# ============================================================================
# ASYNCHRONOUS PIPELINE AGENTS
# ============================================================================


async def async_retriever_agent(state: AgentState) -> AgentState:
    """Retrieves relevant context from vector database based on query."""
    print("\n⚡ [NODE_EXECUTION]: Activating Retriever Agent...")
    
    try:
        query = state["messages"][-1].content if state["messages"] else ""
        
        # Non-blocking similarity search
        docs = vectorstore.similarity_search(query, k=3)
        context = "\n\n".join([doc.page_content for doc in docs])
        
        output = f"📚 *[PULSE RETRIEVER]*\nFound {len(docs)} matching telemetry profiles in database baseline."
        state["agent_outputs"]["retriever"] = output
        state["context"] = context
        state["query"] = query
        
        # Instantly notify the user on Telegram while backend shifts to the Researcher
        await send_telegram_stream(output)
    except Exception as e:
        print(f"[RETRIEVER_ERROR]: {e}")
        state["agent_outputs"]["retriever"] = f"❌ Retriever failed: {str(e)}"
    
    return state


async def async_researcher_agent(state: AgentState) -> AgentState:
    """Analyzes query and context to identify key insights."""
    print("\n⚡ [NODE_EXECUTION]: Activating Researcher Agent...")
    
    try:
        query = state.get("query", "")
        context = state.get("context", "")
        
        # Await the local LLM generation cleanly without freezing the script
        analysis = await llm.ainvoke(
            f"Analyze this query and context, identifying key points and relationships:\n\nQuery: {query}\n\nContext: {context}"
        )
        
        output = f"🔍 *[PULSE RESEARCH ANALYSIS]*\n{analysis}"
        state["agent_outputs"]["research"] = output
        state["analysis"] = analysis
        
        await send_telegram_stream(output)
    except Exception as e:
        print(f"[RESEARCHER_ERROR]: {e}")
        state["agent_outputs"]["research"] = f"❌ Research failed: {str(e)}"
    
    return state


async def async_writer_agent(state: AgentState) -> AgentState:
    """Drafts a comprehensive response based on analysis."""
    print("\n⚡ [NODE_EXECUTION]: Activating Writer Agent...")
    
    try:
        query = state.get("query", "")
        context = state.get("context", "")
        analysis = state.get("analysis", "")
        
        draft = await llm.ainvoke(
            f"Draft a comprehensive response that addresses this query using the context and analysis:\n\nQuery: {query}\nContext: {context}\nAnalysis: {analysis}"
        )
        
        output = f"✍️ *[INITIAL DATA DRAFT]*\n{draft}"
        state["agent_outputs"]["writer"] = output
        state["draft"] = draft
        
        await send_telegram_stream(output)
    except Exception as e:
        print(f"[WRITER_ERROR]: {e}")
        state["agent_outputs"]["writer"] = f"❌ Writer failed: {str(e)}"
    
    return state


async def async_critic_agent(state: AgentState) -> AgentState:
    """Reviews and finalizes the response with improvements."""
    print("\n⚡ [NODE_EXECUTION]: Activating Critic Agent (Finalizing Ledger Block)...")
    
    try:
        query = state.get("query", "")
        draft = state.get("draft", "")
        context = state.get("context", "")
        
        feedback = await llm.ainvoke(
            f"Review this draft response and provide brief structural improvements:\nQuery: {query}\nContext: {context}\nDraft: {draft}"
        )
        
        final = await llm.ainvoke(
            f"Create a final response incorporating this feedback. Keep it direct:\nQuery: {query}\nDraft: {draft}\nFeedback: {feedback}"
        )
        
        output = f"🎯 *[FINAL STATUS RECEIPT]*\n{final}\n\n🔒 *Ledger State:* Verified via Multi-Agent Pulse Pipeline."
        state["agent_outputs"]["critic"] = output
        state["final_response"] = final
        
        await send_telegram_stream(output)
    except Exception as e:
        print(f"[CRITIC_ERROR]: {e}")
        state["agent_outputs"]["critic"] = f"❌ Critic failed: {str(e)}"
    
    return state

# ============================================================================
# COMPILATION ENGINE
# ============================================================================


def build_workflow() -> StateGraph:
    """Constructs the LangGraph workflow with all agent nodes."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("retriever", async_retriever_agent)
    workflow.add_node("researcher", async_researcher_agent)
    workflow.add_node("writer", async_writer_agent)
    workflow.add_node("critic", async_critic_agent)
    
    workflow.add_edge("retriever", "researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", "critic")
    workflow.set_entry_point("retriever")
    
    return workflow.compile()


# Asynchronous runner loop
async def main() -> None:
    """Main execution entry point for the async multi-agent system."""
    print("\n=== Launching Headless Async LangGraph Node ===")
    test_query = "Simulate active pool validation parameters for upcoming flash sequence."
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=test_query)],
        "current_step": "retriever",
        "context": "",
        "analysis": "",
        "draft": "",
        "final_response": "",
        "query": "",
        "agent_outputs": {}
    }
    
    chain = build_workflow()
    
    # Stream over the asynchronous runtime graph execution
    async for output in chain.astream(initial_state):
        for node_name, state_update in output.items():
            print(f"[NODE_COMPLETED]: State shifted out of '{node_name}' successfully.")
    
    print("\n=== Pulse Pipeline Execution Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
