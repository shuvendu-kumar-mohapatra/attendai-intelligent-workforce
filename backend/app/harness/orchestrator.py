import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.models import User, Employee, AuditLog
from app.harness.providers.base import BaseLLMProvider
from app.harness.providers.nvidia import NvidiaNIMProvider
from app.harness.providers.groq import GroqProvider
from app.harness.providers.gemini import GeminiProvider
from app.harness.providers.mock import MockLLMProvider
from app.harness.tool_registry import ToolRegistry, TOOL_DEFINITIONS
from app.harness.permissions import HarnessPermissions
from app.harness.guardrails import HarnessGuardrails
from app.harness.output_validator import OutputValidator

logger = logging.getLogger(__name__)

class AIOrchestrator:
    def __init__(self):
        self._provider = None

    def get_provider(self) -> BaseLLMProvider:
        provider_name = settings.LLM_PROVIDER.lower()
        if provider_name == "nvidia" and settings.NVIDIA_API_KEY:
            return NvidiaNIMProvider()
        elif provider_name == "groq" and settings.GROQ_API_KEY:
            return GroqProvider()
        elif provider_name == "gemini" and settings.GEMINI_API_KEY:
            return GeminiProvider()
        else:
            return MockLLMProvider()

    def get_providers_chain(self) -> List[BaseLLMProvider]:
        chain: List[BaseLLMProvider] = []
        primary = settings.LLM_PROVIDER.lower()

        if primary == "mock":
            return [MockLLMProvider()]

        # Add primary provider first if configured
        if primary == "nvidia" and settings.NVIDIA_API_KEY:
            chain.append(NvidiaNIMProvider())
        elif primary == "groq" and settings.GROQ_API_KEY:
            chain.append(GroqProvider())
        elif primary == "gemini" and settings.GEMINI_API_KEY:
            chain.append(GeminiProvider())

        # Add secondary fallback providers
        if settings.GROQ_API_KEY and not any(isinstance(p, GroqProvider) for p in chain):
            chain.append(GroqProvider())
        if settings.NVIDIA_API_KEY and not any(isinstance(p, NvidiaNIMProvider) for p in chain):
            chain.append(NvidiaNIMProvider())

        # Ultimate offline fallback
        chain.append(MockLLMProvider())
        return chain

    async def generate_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        override_provider: Optional[BaseLLMProvider] = None
    ) -> tuple[Dict[str, Any], BaseLLMProvider, bool]:
        """
        Executes LLM generation with automatic provider failover.
        Returns (response_dict, active_provider, was_fallback_used).
        """
        if override_provider:
            resp = await override_provider.generate_response(messages=messages, tools=tools)
            return resp, override_provider, False

        providers = self.get_providers_chain()
        for i, provider in enumerate(providers):
            try:
                resp = await provider.generate_response(messages=messages, tools=tools)
                return resp, provider, (i > 0)
            except Exception as e:
                logger.warning(
                    f"LLM Provider '{type(provider).__name__}' failed: {e}. "
                    f"Attempting fallback to next provider in chain."
                )
                continue

        mock = MockLLMProvider()
        resp = await mock.generate_response(messages=messages, tools=tools)
        return resp, mock, True

    async def execute_turn(
        self,
        db: AsyncSession,
        user: User,
        employee: Optional[Employee],
        user_message: str,
        conversation_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes a complete AI turn with intent understanding, multi-step tool reasoning,
        conversational memory, strict RBAC, and executive presentation rendering.
        """
        # 1. Guardrails check
        is_safe, reason = HarnessGuardrails.inspect_input(user_message)
        if not is_safe:
            return {
                "content": f"Security Notice: Request blocked by AttendAI AI harness. {reason}",
                "tool_calls": [],
                "tool_results": [],
                "citations": [],
                "follow_ups": [],
                "model": "attendai-guardrails",
                "provider": "security_harness",
                "fallback_used": False,
                "latency_ms": 1.0
            }

        # 2. Build enterprise system instructions with role-aware boundaries
        role_label = user.role.replace("_", " ").title()
        
        scope_instructions = ""
        if user.role == "admin":
            scope_instructions = (
                "You have organization-wide administrative scope. You can analyze any department, "
                "compare cross-department trends, inspect clock-in timings, query overtime, evaluate long breaks, "
                "track missing clock-outs, analyze leave patterns, and investigate anomaly flags."
            )
        elif user.role == "hr_manager":
            scope_instructions = (
                "You have HR Manager scope. You can analyze workforce attendance, overtime, absenteeism, "
                "compare department metrics, analyze leave trends, investigate anomalies, and review policy compliance."
            )
        else:  # employee
            emp_name = f"{employee.first_name} {employee.last_name}" if employee else user.email
            scope_instructions = (
                f"You have personal Employee scope for '{emp_name}'. "
                "You can access your personal attendance records, personal overtime, personal late arrivals, "
                "personal working hours, leave balances, assigned shift schedule, and company HR policies. "
                "Under NO circumstances should you access, reveal, or attempt to query records of other colleagues or organizational summaries. "
                "Always use 'get_my_*' personal tools for personal questions."
            )

        system_prompt = (
            f"You are AttendAI Assistant, an elite enterprise workforce intelligence analyst and AI advisor.\n"
            f"Authenticated User: '{user.email}' | Role: '{role_label}'.\n"
            f"Scope: {scope_instructions}\n\n"
            "CRITICAL OPERATIONAL & PRESENTATION GUIDELINES:\n"
            "1. UNIVERSAL QUERY UNDERSTANDING: Understand arbitrary, previously unseen natural-language workforce inquiries. "
            "Dynamically interpret intents regarding employee profiles, attendance, punctuality, clock-in times (e.g. after 11), "
            "worked hours (e.g. > 45 hrs), break durations, weekend overtime, shift patterns, leave balances, department comparisons, and policy rules.\n"
            "2. ROLE-BASED TOOL SELECTION:\n"
            "   - If role is 'employee', ALWAYS select 'get_my_*' tools for personal attendance, overtime, hours, leave balances, and shifts. Never attempt org-wide tools.\n"
            "   - If role is 'admin' or 'hr_manager', select universal query tools ('query_workforce_attendance', 'compare_workforce_metrics', 'query_leave_analytics', etc.) as appropriate.\n"
            "3. EXACT NUMERICAL & DATE CONDITIONS:\n"
            "   - 'more than 5' means > 5 (count >= 6).\n"
            "   - 'at least 3' means >= 3.\n"
            "   - 'more than 45 hours' means worked_hours >= 45.0.\n"
            "   - Respect exact time periods: 'previous quarter', 'this year', 'today', 'last month'. Never substitute a 7-day query for a monthly/quarterly query.\n"
            "4. MULTI-STEP REASONING: When an inquiry requires comparisons or compound criteria (e.g. comparing two lowest departments, or finding departments with increasing absenteeism), invoke the appropriate tools, compare metrics, and cite evidence.\n"
            "5. NEVER OUTPUT RAW JSON: Under NO circumstances should you output raw JSON, Python dictionaries, or technical traces to the user.\n"
            "6. POLISHED ENTERPRISE FORMATTING:\n"
            "   - Synthesize all data into clean Markdown tables with bold column headers.\n"
            "   - Include highlighted KPI metrics, bulleted summaries, and bold percentages.\n"
            "   - Include an '### AI Insight' or '### Key Observation' section grounded in verified database evidence.\n"
            "   - Ground all factual statements in verified tool outputs. Never fabricate employees, dates, or metrics.\n"
            "7. ERROR & SCOPE BOUNDARIES: If an operation is denied or fails, explain the permission boundary clearly and courteously without claiming data was retrieved."
        )

        messages = [{"role": "system", "content": system_prompt}]
        
        # Incorporate recent conversation context (last 8 messages)
        for hist in conversation_history[-8:]:
            messages.append({"role": hist["role"], "content": hist["content"]})
        messages.append({"role": "user", "content": user_message})

        # Filter permitted tools for the user role
        allowed_tools = HarnessPermissions.filter_tools_for_user(user.role, TOOL_DEFINITIONS)

        # 3. Multi-Step Tool Reasoning Loop (Max 3 turns)
        MAX_TOOL_LOOPS = 3
        current_loop = 0
        all_tool_calls = []
        all_tool_results = []
        active_provider = None
        fallback_used = False
        final_content = ""
        total_latency = 0.0

        while current_loop < MAX_TOOL_LOOPS:
            current_loop += 1
            
            resp, prov, fb = await self.generate_with_fallback(
                messages=messages,
                tools=allowed_tools if allowed_tools else None
            )
            active_provider = prov
            if fb:
                fallback_used = True
            total_latency += resp.get("latency_ms", 0)

            tool_calls = resp.get("tool_calls")
            
            if not tool_calls:
                # No more tools called; model completed response
                final_content = resp.get("content") or ""
                break
                
            all_tool_calls.extend(tool_calls)
            
            # Execute all tool calls in this batch
            batch_tool_results = []
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                # Check permission
                if not HarnessPermissions.is_tool_allowed(user.role, func_name):
                    res = {"error": f"Permission denied: role '{user.role}' cannot invoke tool '{func_name}'"}
                else:
                    res = await ToolRegistry.execute_tool(
                        name=func_name,
                        arguments=args,
                        db=db,
                        user=user,
                        employee=employee
                    )

                # Record audit log
                audit = AuditLog(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    action=f"AI_TOOL_CALL:{func_name}",
                    resource_type="ai_harness",
                    resource_id=func_name,
                    details={"arguments": args, "result_preview": str(res)[:300]}
                )
                db.add(audit)

                tool_item = {
                    "tool_call_id": tc.get("id"),
                    "tool_name": func_name,
                    "output": res
                }
                all_tool_results.append(tool_item)
                batch_tool_results.append(tool_item)

            await db.commit()

            # Append assistant message with tool_calls and tool results
            messages.append({
                "role": "assistant",
                "content": resp.get("content") or "",
                "tool_calls": tool_calls
            })
            for tr in batch_tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": json.dumps(tr["output"])
                })

            # Prompt model to synthesize the tool results into a polished enterprise markdown response
            has_error = any("error" in tr.get("output", {}) for tr in all_tool_results)
            if has_error:
                synthesis_instruction = (
                    "Please respond to the user based on the tool results above. "
                    "NOTICE: A requested operation encountered an authorization or validation error. "
                    "Politely and clearly explain the restriction or error to the user based on their role permissions. "
                    "Do NOT claim that data was retrieved or that all metrics were verified when a tool returned an error. "
                    "Do not output raw JSON."
                )
            else:
                synthesis_instruction = (
                    "Please synthesize the above verified database records into a polished enterprise markdown response "
                    "with clean markdown tables, bullet points, key observations, and actionable insights. Do not output raw JSON."
                )

            messages.append({
                "role": "user",
                "content": synthesis_instruction
            })
            final_resp, prov, fb = await self.generate_with_fallback(messages=messages, tools=None)
            if fb:
                fallback_used = True
            final_content = final_resp.get("content") or ""
            total_latency += final_resp.get("latency_ms", 0)
            break

        # If LLM returned empty content after tools, synthesize via OutputValidator
        if not final_content and all_tool_results:
            final_content = OutputValidator._synthesize_tool_results_to_markdown(all_tool_results)

        # 4. Sanitize, Validate, and Structure Presentation
        final_content = HarnessGuardrails.sanitize_output(final_content)
        validated = OutputValidator.validate_and_format(final_content, all_tool_results, user.role)

        provider_tag = "nvidia" if isinstance(active_provider, NvidiaNIMProvider) else (
            "groq" if isinstance(active_provider, GroqProvider) else (
                "gemini" if isinstance(active_provider, GeminiProvider) else "mock"
            )
        )
        model_tag = getattr(active_provider, "model", "default")

        return {
            "content": validated["validated_text"],
            "tool_calls": all_tool_calls,
            "tool_results": all_tool_results,
            "citations": validated["citations"],
            "follow_ups": validated["follow_ups"],
            "model": model_tag,
            "provider": provider_tag,
            "fallback_used": fallback_used,
            "latency_ms": round(total_latency, 2)
        }

ai_orchestrator = AIOrchestrator()
