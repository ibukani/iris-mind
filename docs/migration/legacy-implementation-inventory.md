# Legacy Implementation Inventory (HISTORICAL)

> **Warning**: This document describes code that has been deleted (Phase 12).
> All legacy packages (`iris/limbic/`, `iris/memory/`, `iris/agency/`, `iris/llm/`,
> `iris/event/`, `iris/kernel/plugin/`, etc.) no longer exist in this repository.
> This document is retained for historical reference only.

## Summary

This document inventories legacy implementation across `iris/limbic/`, `iris/memory/`, `iris/agency/`, `iris/llm/`, `iris/event/`, and `iris/kernel/plugin/` before Phase 6 affect/appraisal migration to Cognitive Runtime Architecture v1.2.1.

The legacy codebase is a Plugin/EventBus-centered system where limbic (appraisal, mood, relationship) is orchestrated by `LimbicOrchestrator` driven by `_LimbicEventHandler` through `EventBus` subscriptions. Memory, agency, and limbic are implicitly coupled via event chains, shared managers, and service locator (`PluginManager.resolve()`).

The new v1.2.1 target already provides the typed scaffold (`AffectSnapshot`, `RelationshipSnapshot`, `AppraisalResult`, `RelationshipResult`, `FrameBuilder` mappings) but lacks concrete `PipelineStep` implementations for affect/relationship, dedicated contracts, and wiring.

## Migration status

| Legacy area | Current responsibility | New target location | Status | Priority | Notes |
|---|---|---|---|---|---|
| `limbic/appraiser.py` | Lazarus Primary+Secondary appraisal → CAPE 6 dimensions | `cognitive/affect/appraisal.py` | Not migrated | High | Core Phase 6 work; migrate simplified rule-based version |
| `limbic/classifier.py` | Neural emotion classification (transformers) | Deferred | Not migrated | Low | Heavy dependency; defer, use keyword-only in Phase 6 |
| `limbic/generator.py` | AppraisalDimensions → CompanionEmotion (Plutchik+VAD) | `cognitive/affect/appraisal.py` | Not migrated | High | Core Phase 6 work; simplified version |
| `limbic/mood.py` | Time-decay mood (10min half-life) | `cognitive/affect/mood.py` | Not migrated | High | Core Phase 6 work |
| `limbic/relationship.py` | Per-account trust/familiarity/disclosure/attachment | `cognitive/affect/relationship.py` | Not migrated | High | Core Phase 6 work |
| `limbic/state.py` | EmotionStateManager (latest + history 50) | `cognitive/affect/` | Not migrated | Medium | Simple state holder; may not need full history |
| `limbic/orchestrator.py` | Full pipeline orchestration + EventBus handler | Discard as orchestration | Not migrated | High (avoid) | Do NOT migrate `LimbicOrchestrator`; CognitiveCycle replaces orchestration |
| `limbic/handler.py` | EventBus subscription → LimbicOrchestrator | Forbidden pattern | Not migrated | High (avoid) | EventBus-driven orchestration is explicitly forbidden in v1.2.1 |
| `limbic/stores/appraisal_store.py` | AppraisalEpisode JSONL persistence | Deferred | Not migrated | Low | Persistence can come after core logic works |
| `limbic/stores/relationship_store.py` | RelationshipSnapshot JSONL persistence | Deferred | Not migrated | Low | Persistence can come after core logic works |
| `limbic/models.py` | Pydantic models (PrimaryAppraisal, SecondaryAppraisal, CompanionEmotion, Mood, RelationshipState, EmotionResult) | `contracts/affect.py` + `cognitive/affect/` | Partially | High | Move core types to contracts; keep implementation details in cognitive |
| `limbic/lexicon.py` | Keyword map + EmotionClassifierProtocol | `cognitive/affect/` | Not migrated | Medium | Useful as fallback classifier |
| `limbic/__init__.py` | LimbicPlugin (PluginProtocol entry) | Discard | Not migrated | High (avoid) | Plugin pattern is forbidden |
| `memory/` (various) | Sensory, short-term, long-term, procedural, archive, consolidation, LangMem | `cognitive/memory/`, `adapters/stores/`, `features/memory_consolidation/` | Partially (Phase 5/5.5) | High | See Memory review section |
| `agency/` | Planning, inhibition, execution, modulation, proactive | `cognitive/policy/`, `cognitive/action/`, `features/proactive_talk/` | Not migrated | Medium | Phase 7 target; do not mix into Phase 6 |
| `llm/` (various) | Provider clients, prompt building, context, repetition, tokens | `adapters/llm/`, `cognitive/action/response.py` | Partially (Phase 4/4.5) | High | See LLM review section |
| `event/` | EventBus main control flow | Retire / telemetry only | Not migrated | High (avoid) | Forbidden for CognitiveCycle orchestration |
| `kernel/plugin/` | PluginManager, hooks, service locator | Discard entirely | Not migrated | High (avoid) | Forbidden in v1.2.1 |

## Limbic review

### Responsibilities found

| Responsibility | File | Key classes/functions | Complexity |
|---|---|---|---|
| Appraisal (Lazarus) | `appraiser.py` | `Appraiser.appraise_primary()`, `.appraise_secondary()`, `.compute_dimensions()` | Medium (rule-based heuristics) |
| Appraisal dimensions | `models.py` | `PrimaryAppraisal`, `SecondaryAppraisal`, `AppraisalDimensions` (CAPE 6) | Low (data models) |
| Emotion classification (neural) | `classifier.py` | `NeuralEmotionClassifier` (transformers pipeline) | High (heavy dep: torch, transformers) |
| Emotion classification (keyword) | `lexicon.py` | `KEYWORD_MAP`, `EmotionClassifierProtocol` | Low |
| Emotion generation | `generator.py` | `EmotionGenerator.generate()` (weighted linear sum + mood blend) | Low (pure math) |
| Emotion state model | `models.py` | `CompanionEmotion`, `PlutchikEmotion`, `PLUTCHIK_VAD` | Low |
| Mood dynamics | `mood.py` | `MoodDynamics.update()`, `._compute_decay()` | Low (exponential decay) |
| Mood model | `models.py` | `Mood` (valence, arousal, dominance, last_updated) | Low |
| Relationship state | `relationship.py` | `RelationshipManager` (per-account trust/familiarity/disclosure/level/attachment) | Medium |
| Relationship model | `models.py` | `RelationshipState`, `RelationshipLevel`, `AttachmentStyle` | Low |
| Internal state | `state.py` | `EmotionStateManager` (latest + 50 history) | Low |
| Orchestration | `orchestrator.py` | `LimbicOrchestrator.process()` (10-step pipeline) | High (do NOT migrate) |
| Event handler | `handler.py` | `_LimbicEventHandler` (EventBus subscription) | High (do NOT migrate) |
| Appraisal store | `stores/appraisal_store.py` | `AppraisalEpisodeStore` (JSONL) | Low (defer) |
| Relationship store | `stores/relationship_store.py` | `RelationshipStateStore` (JSONL) | Low (defer) |
| Plugin entry | `__init__.py` | `LimbicPlugin` (PluginProtocol) | High (do NOT migrate) |

### Recommended target mapping

| Legacy concept | Target location | Notes |
|---|---|---|
| `PrimaryAppraisal`, `SecondaryAppraisal`, `AppraisalDimensions` | `contracts/affect.py` | Shared contracts for affect domain |
| `CompanionEmotion`, `PlutchikEmotion`, `PLUTCHIK_VAD` | `contracts/affect.py` | Core emotion types |
| `Mood` | `contracts/affect.py` | Core mood type |
| `RelationshipState`, `RelationshipLevel`, `AttachmentStyle` | `contracts/affect.py` | Core relationship types |
| `EmotionResult` | Discard | CognitiveCycle replaces with typed AppraisalResult + RelationshipResult |
| `Appraiser.appraise_primary/secondary` | `cognitive/affect/appraisal.py` | Simplified rule-based appraisal |
| `EmotionGenerator.generate` | `cognitive/affect/appraisal.py` | Generation as part of AppraisalStep |
| `MoodDynamics` | `cognitive/affect/mood.py` | Simple exponential decay |
| `RelationshipManager` | `cognitive/affect/relationship.py` | Per-account state, simplified trust/familiarity |
| `EmotionStateManager` | `cognitive/affect/` | Simple latest-state holder (may skip history) |
| `NeuralEmotionClassifier` | Deferred | Heavy dependency; not needed for MVP |
| `AppraisalEpisodeStore` | Deferred | Persistence after core logic |
| `RelationshipStateStore` | Deferred | Persistence after core logic |
| `LimbicOrchestrator` | Discard | CognitiveCycle replaces orchestration |
| `_LimbicEventHandler` | Discard | EventBus-driven orchestration forbidden |
| `LimbicPlugin` | Discard | Plugin pattern forbidden |

### Risks before Phase 6

1. **Legacy stores depend on `iris.memory.langmem.stores._IdIndexedJsonlStore`** — `AppraisalEpisodeStore` and `RelationshipStateStore` both inherit from LangMem's JSONL base. If we later migrate persistence, we must decouple from LangMem store base.

2. **`LimbicOrchestrator` is the single source of truth** for modulation state consumed by `iris/agency/`. During Phase 6, the limbic → agency modulation bridge will be broken until agency is migrated (Phase 7). The legacy `agency/planning/handler.py` directly calls `limbic.orchestrator.LimbicOrchestrator.get_modulation_state()`.

3. **`LimbicOrchestrator` mixes appraisal, mood, relationship, and state into one pipeline** — the legacy orchestrator calls all sub-components sequentially and returns a unified `EmotionResult`. Phase 6 must split these into separate `PipelineStep` instances orchestrated by `CognitiveCycle`.

4. **No existing affect/relationship stores in v1.2.1** — if Phase 6 needs persistence, it must be designed from scratch, not importing legacy JSONL stores.

### Recommended Phase 6 scope

The smallest safe Phase 6:

1. **Create `contracts/affect.py`** with core types (AffectState, MoodState, RelationshipState, AppraisalDimensions, EmotionLabel enum, VAD tuple)
2. **Create `cognitive/affect/appraisal.py`** with `AppraisalStep(PipelineStep[AppraisalResult])`:
   - Keyword-based emotion classification (from `limbic/lexicon.py`)
   - Simplified VAD mapping
   - No neural classifier
3. **Create `cognitive/affect/mood.py`** with `MoodDynamics` (exponential decay):
   - Updated in a `LearningHook` after `ActionResult`
   - Not a PipelineStep (mood is slow-moving, updated asynchronously)
4. **Create `cognitive/affect/relationship.py`** with `RelationshipStep(PipelineStep[RelationshipResult])`:
   - Per-user identity state (in-memory dict)
   - Simplified trust/familiarity deltas based on interaction
   - No attachment style or disclosure depth for MVP
5. **Wire into `CognitiveCycle`** via `runtime/wiring/cognitive.py`

## Memory review

### Responsibilities found

| Responsibility | Legacy location | Status | Notes |
|---|---|---|---|
| Sensory memory | `memory/sensory/` (8 files) | Not migrated | Includes fragment assembly, readiness, pending, EventBus hooks |
| Short-term memory | `memory/short_term/` (13 files) | Not migrated | Turns, topics, entities, importance, presence, search |
| Episodic memory | `memory/long_term/stores.py` (EpisodicStore) | Not migrated | JSONL persistence |
| Semantic memory | `memory/long_term/stores.py` (SemanticStore) + `vector_store.py` | Not migrated | JSONL + ChromaDB + BM25 hybrid |
| Goal store | `memory/long_term/goal_store.py` | Not migrated | In-memory goal persistence with decay |
| Procedural memory (style) | `memory/procedural/style_store.py` + `style_index.py` | Not migrated | JSONL style memory with scope filter |
| Procedural memory (persona patch) | `memory/procedural/persona_patch_store.py` | Not migrated | Candidate-based persona modification |
| Conversation archive | `memory/archive/` (5 files) | Not migrated | Append-only JSONL, date rotation |
| Consolidation audit | `memory/consolidation/` (3 files) | Not migrated | Audit log for promotion events |
| LangMem extraction | `memory/langmem/extractor.py` | Not migrated | LLM-based extraction across 6 pass types |
| LangMem promotion | `memory/langmem/promotion.py` + `handlers.py` | Not migrated | Candidate → target store promotion |
| LangMem pipeline | `memory/langmem/pipeline.py` | Not migrated | Full orchestration of extraction + promotion |
| LangMem scheduler | `memory/langmem/scheduler.py` | Not migrated | Background async scheduling |
| Memory facade | `memory/manager.py` + `dispatcher.py` | Not migrated | Unified MemoryManager (sensory + short + long) |
| Legacy ↔ Limbic bridge | `memory/langmem/handlers.py` | Deferred | Imports `iris.limbic.relationship.RelationshipManager` for promotion |

### Already covered by Phase 5 / 5.5

| Capability | New target location | Status |
|---|---|---|
| Memory contract types | `contracts/memory.py` (`MemoryRecord`, `MemoryQuery`, `MemorySearchResult`) | Done (Phase 5) |
| MemoryStore port | `adapters/memory/ports.py` (`MemoryStore`) | Done (Phase 5) |
| FakeMemoryStore | `adapters/memory/fake.py` | Done (Phase 5) |
| InMemoryVectorMemoryStore | `adapters/memory/vector.py` | Done (Phase 5.5) |
| LangChainMemoryStore | `adapters/memory/langchain.py` | Done (Phase 5.5) |
| MemoryRetrievalStep | `cognitive/memory/retrieval.py` | Done (Phase 5) |
| MemoryRetriever protocol | `cognitive/memory/retrieval.py` | Done (Phase 5) |
| Wiring helpers | `runtime/wiring/memory.py` | Done (Phase 5) |

### Missing pieces

1. **Sensory memory** (not in Phase 5/5.5, no plans before Phase 8 or later)
2. **Short-term memory** (turns, topics, entities, context rendering — not in Phase 5/5.5)
3. **Episodic/Semantic JSONL stores** (Phase 5 only has vector-based stores, no JSONL)
4. **Episodic/Semantic search logic** (legacy has sophisticated search; Phase 5 delegates to vector store)
5. **Goal store** (not in any phase plan)
6. **Procedural memory (style + persona patch)** (not in any phase plan)
7. **Conversation archive** (not in any phase plan)
8. **Consolidation audit** (not in any phase plan)
9. **LangMem extraction/promotion** (explicitly deferred by Phase 5 instructions: "LangMem promotion/consolidation、実 embeddings provider、vector DB persistence、旧 LangChain memory API の core memory 化は後続 phase まで入れない")

### Deferred pieces

| Piece | Reason |
|---|---|
| LangMem extraction | Heavy LLM dependency; deferred to later phases |
| Long-term memory promotion | Not needed for MVP one-turn flow |
| Sensory memory | Complex fragment assembly / readiness; defer to proactive phase |
| Short-term memory context rendering | Not yet wired; may be needed for response prompt enhancement |
| Archive | Append-only log; useful but not critical for affect |
| Procedural memory | Style/persona are Phase 9+ features |
| Consolidation audit | Audit logging, can be added later |

**Important:** Do not mix memory promotion/consolidation into Phase 6 affect/appraisal. These are separate concerns handled by future phases.

## Agency review

### Responsibilities found

| Responsibility | Legacy location | Complexity | Phase |
|---|---|---|---|
| Planning (response strategy) | `planning/strategies/response.py` | Medium | Phase 7 |
| Planning (proactive strategy) | `planning/strategies/proactive.py` | Medium | Phase 8 |
| Context hint building | `planning/context/builder.py` + 7 providers | High | Phase 7 |
| Proactive judge/scorer | `planning/decisions/judge.py`, `scorer.py` | Medium | Phase 8 |
| Inhibition (gate/striatum) | `inhibition/` (6 files) | Medium | Phase 7 |
| Execution (LangGraph) | `execution/orchestrator.py` + 5 nodes | High | Phase 7 |
| Modulation state | `modulation/state.py` | Low | Phase 7 |
| Modulation behavior policy | `modulation/behavior_policy.py` | Medium | Phase 7 |
| Modulation prompt guidance | `modulation/prompt_guidance.py` | Low | Phase 7 |
| Task level policy | `task_level.py` | Low | Phase 7 |
| Internal bus (plan→exec) | `internal_bus.py` | Low | Discard pattern |
| LLM gateway | `execution/llm/gateway.py` | High | Phase 7 |

### Recommended target mapping

| Legacy concept | Target location | Notes |
|---|---|---|
| `PlanningManager` | `cognitive/policy/` | Simplified planning step |
| `InhibitionManager` | `cognitive/policy/inhibition/` | Separate inhibition as typed policy constraints |
| `ExecutionOrchestrator` | `cognitive/action/` | Action execution as PipelineStep |
| `FlowExecutor` | `cognitive/action/` | Simplified execution step |
| `ModulationState` | `cognitive/affect/` (mood) + `cognitive/policy/` (chaos) | Split into affect-derived and policy-derived parts |
| `ProactiveJudge/Scorer` | `features/proactive_talk/` | Feature-level, not cognitive-level |
| `QuestionGenerator` | `features/proactive_talk/` | Feature-level |
| `InternalBus` | Discard | CognitiveCycle replaces inter-module communication |

### What must not be mixed into affect/appraisal

1. **Inhibition/gate control** — Do not move `inhibition/gate.py` or `inhibition/striatum.py` into affect. Inhibition is a Policy concern (Phase 7).
2. **Execution/LangGraph** — Do not move `execution/orchestrator.py` or execution nodes into affect. Execution is an Action concern (Phase 7).
3. **Proactive scoring/judging** — Do not move `ProactiveScorer` or `ProactiveJudge` into affect. Proactive is a Feature (Phase 8).
4. **Context hint building** — Do not move `ContextHintBuilder` into affect. Context is a perception/planning concern.
5. **Question generation** — Do not move `QuestionGenerator` into affect. It is a proactive feature component.
6. **Modulation behavior policy** (`should_suppress_proactive`, `topic_jump_prob`, etc.) — These are action policy decisions, not affect state.

**Exception:** A `ModulationState` typed placeholder may exist in `contracts/affect.py` if CognitiveCycle requires it, but the actual modulation logic stays out of Phase 6.

## LLM review

### Responsibilities found

| Responsibility | Legacy location | Status | Notes |
|---|---|---|---|
| Multi-provider routing | `bridge.py` | Deferred | Phase 4 uses `adapters/llm/` with OpenAI + Fake only |
| Ollama provider | `providers/ollama/` (6 files) | Deferred | Not covered by Phase 4 |
| OpenAI-compatible provider | `providers/openai_compatible.py` | Already covered | Phase 4.5 has `adapters/llm/openai.py` |
| Google provider | `providers/openai_compatible.py` | Deferred | Same file as OpenAI-compatible |
| OpenRouter provider | `providers/openai_compatible.py` | Deferred | Same file as OpenAI-compatible |
| Provider auto-discovery | `providers/discovery.py` + `registry.py` | Discard | Phase 4 uses explicit wiring, not discovery |
| Provider base/abstract | `providers/base.py` | Discard | Phase 4 uses `LLMClient` protocol instead |
| System prompt building | `prompt.py` (`Personality`) | `cognitive/action/response.py` | Phase 4 already has `ResponsePrompt` |
| Context window compression | `context.py` | Deferred | May become `cognitive/action/` or adapter-level |
| Repetition detection | `repetition.py` | Reusable as-is | Utility; no limbic/memory/agency deps |
| Token estimation | `token_utils.py` + `tokenizer.py` | Reusable as-is | Utility; no limbic/memory/agency deps |
| LLM capability check | `capability.py` | Deferred | Model capability introspection |
| Priority lock | `priority_lock.py` | Reusable as-is | Utility; no limbic/memory/agency deps |
| Interrupt token | `interrupt_token.py` | Reusable as-is | Utility; no limbic/memory/agency deps |

### Already covered by Phase 4 / 4.5

| Capability | New target location | Status |
|---|---|---|
| LLM client protocol | `adapters/llm/ports.py` (`LLMClient`) | Done |
| OpenAI provider | `adapters/llm/openai.py` (`OpenAILLMClient`) | Done |
| Fake LLM client | `adapters/llm/fake.py` (`FakeLLMClient`) | Done |
| Response generation prompt | `cognitive/action/response.py` (`ResponsePrompt`, `build_response_prompt`) | Done |
| Response generation step | `cognitive/action/response.py` (`ResponseGenerationStep`) | Done |
| LLM wiring | `runtime/wiring/llm.py` | Done |

### Reusable pieces

These files have zero imports from legacy modules (limbic, memory, agency, event) and can be reused directly:

| File | Purpose | Reuse plan |
|---|---|---|
| `llm/repetition.py` | RepetitionDetector | Reuse as-is in LLM adapters or cognitive action |
| `llm/token_utils.py` | Token estimation | Reuse as-is |
| `llm/tokenizer.py` | TokenizerManager | Reuse as-is |
| `llm/priority_lock.py` | Priority lock | Reuse as-is |
| `llm/interrupt_token.py` | Cancel token | Reuse as-is |

### Deferred pieces

| File | Reason |
|---|---|
| `llm/providers/ollama/` | Ollama adapter; not needed until Ollama is the LLM backend |
| `llm/context.py` | Context window compression; not needed for MVP one-turn flow |
| `llm/capability.py` | Model capability introspection; not needed for MVP |
| `llm/prompt.py` | Personality template; Phase 4 already has `build_response_prompt` |
| `llm/bridge.py` | Legacy orchestration (LLMBridge); Phase 4 uses direct `LLMClient` protocol |

## Event / Plugin / Kernel review

### Legacy orchestration assumptions

| Assumption | Location | Conflict with v1.2.1 |
|---|---|---|
| EventBus is the main control flow | `event/event_bus.py` | Section 8: "EventBus による主制御" eliminated |
| PluginManager as composition root | `kernel/manager.py` | Section 8: "PluginManager 中心の設計" eliminated |
| Service locator (`resolve`, `resolve_optional`) | `kernel/plugin/service_container.py` | Rule #14: explicitly prohibited |
| Hook-based pipeline interception | `kernel/plugin/hooks.py`, `hook_points.py` | Replaced by `FeatureDefinition` + typed `PipelineStep` |
| Plugin manifest/dependency graph | `kernel/plugin/manifest.py`, `lifecycle/dependency.py` | Replaced by explicit `runtime/wiring/` |
| Plugin protocol with manager injection | `kernel/plugin/protocol.py` | Replaced by constructor injection |
| Global event type registry | `event/base.py` (`_type_registry`) | Rule #14: no global registries |
| Event type aggregation shim | `event/event_types.py` | Section 8: explicitly listed for elimination |
| Kernel mutable global state | `kernel/plugin/kernel_state.py` | Replaced by per-turn `WorkspaceFrame` |
| Filesystem-based plugin discovery | `kernel/plugin/loader.py` | Replaced by explicit registration |
| Phase-ordered initialization | `kernel/plugin/lifecycle/` | Replaced by explicit wiring order |
| Memory/limbic/agency event coupling | All `handler.py` files + `event/event_types.py` | Section 8: "memory/limbic/agency が暗黙に EventBus で連携する構造" eliminated |

### Target architecture conflicts

All of `iris/event/` and `iris/kernel/plugin/` are fundamentally incompatible with v1.2.1 architecture. These directories should remain as legacy migration reference only. No new target module should import from them.

Specific violations if used as target:
- `event/event_bus.py` — `CognitiveCycle` must not use EventBus for pipeline control
- `kernel/plugin/hooks.py` — `@hook` decorator creates hidden interception chains
- `kernel/plugin/service_container.py` — `resolve()` and `resolve_optional()` are explicitly prohibited
- `kernel/manager.py` — `PluginManager` as DI container is the opposite of constructor injection

### Safe reuse guidance

| Item | Safe to reference? | Notes |
|---|---|---|
| `event/base.py` `Event` base class | No | Legacy type; use `Observation` instead |
| `event/event_bus.py` `EventBus` | No | Forbidden for main control flow |
| `kernel/plugin/hooks.py` `@hook` | No | Replaced by `PipelineStep` + `FeatureDefinition` |
| `kernel/plugin/service_container.py` | No | Service locator prohibited |
| `kernel/plugin/manifest.py` | No | Plugin manifests eliminated |
| `kernel/manager.py` | No | PluginManager eliminated |

## Recommended Phase 6 plan

### Phase 6 scope (minimal safe)

1. **`contracts/affect.py`** — Core affect types:
   - `EmotionLabel` (StrEnum) — basic emotions (joy, sadness, anger, fear, surprise, disgust, trust, anticipation, neutral)
   - `VAD` (dataclass, frozen) — valence/arousal/dominance
   - `MoodState` (dataclass, frozen) — mood_label, vAd
   - `RelationshipState` (dataclass, frozen) — affinity, trust, familiarity
   - `AffectState` (dataclass, frozen) — current emotion, mood, VAD

2. **`cognitive/affect/appraisal.py`** — `AppraisalStep(PipelineStep[AppraisalResult])`:
   - Keyword-based emotion classification (from `limbic/lexicon.py`, no transformers)
   - VAD lookup from keyword/emotion mapping
   - Simplified primary appraisal (novelty/pleasantness heuristics)
   - Returns `AppraisalResult` with mood_label, arousal, valence

3. **`cognitive/affect/relationship.py`** — `RelationshipStep(PipelineStep[RelationshipResult])`:
   - In-memory per-user state (dict keyed by `user_id`)
   - Simplified trust/affinity/familiarity deltas
   - Returns `RelationshipResult`

4. **`cognitive/affect/mood.py`** — `MoodDynamics` (not a PipelineStep; updated via LearningHook):
   - Exponential decay of mood toward neutral
   - Moved by emotion each cycle

5. **Update `cognitive/cycle/frame_builder.py`** — verify `AppraisalResult` and `RelationshipResult` mapping (already scaffolded, may need minor updates for new field names)

6. **Update `runtime/wiring/cognitive.py`** — add `wire_affect_aware_cognitive_cycle()` or similar that includes appraisal + relationship steps

7. **Update `contracts/affect.py` imports** in frame.py if needed

### What Phase 6 MUST NOT include

- ❌ `NeuralEmotionClassifier` (transformers/torch) — defer
- ❌ `LimbicOrchestrator` — discard; CognitiveCycle orchestrates
- ❌ `_LimbicEventHandler` — discard; EventBus forbidden
- ❌ `LimbicPlugin` — discard; Plugin pattern forbidden
- ❌ `AppraisalEpisodeStore` / `RelationshipStateStore` — defer persistence
- ❌ EventBus subscriptions for affect updates
- ❌ Emotion history (50-turn history) — defer if not needed
- ❌ Full Lazarus appraisal (goal_relevance, agency, coping_potential) — simplified only
- ❌ Attachment style — defer
- ❌ Disclosure depth tracking — defer
- ❌ Any import from `iris/limbic/`, `iris/event/`, `iris/kernel/plugin/`
- ❌ Any import from `iris/agency/` (including `ModulationState`)
- ❌ Any import from `iris/memory/` (affect should not call memory directly)

## Deferred work

Items that must NOT be done in Phase 6:

| Item | Reason | Future phase |
|---|---|---|
| Neural emotion classifier | Heavy deps (torch, transformers); overkill for MVP | Post-MVP |
| Persistence (appraisal/relationship stores) | Not needed for turn-level correctness; add after core logic works | Phase 6.x or Phase 9 |
| Full Lazarus appraisal model | 5+ dimension scoring is unnecessary for MVP; simplified heuristics suffice | Phase 6.x |
| Attachment style modeling | Complex psychological model; no MVP requirement | Phase 6.x |
| Disclosure depth tracking | Requires long-term per-user tracking; defer | Phase 6.x |
| Emotion history (50 turns) | Not needed unless downstream steps query past affect | Phase 6.x |
| ModulationState → agency bridge | Agency not migrated yet; ModulationState will be reconstructed in Phase 7 | Phase 7 |
| LangMem limbic extraction | `memory/langmem/schemas.py` has `AppraisalMemoryCandidate`, `RelationshipMemoryCandidate` — these are LangMem-specific, not Phase 6 | Phase 9 |
| LangMem limbic promotion handlers | `memory/langmem/handlers.py` references `RelationshipManager` and `AppraisalEpisodeStore` — these are legacy. New handlers will be written post-migration | Phase 9 |
| All `iris/agency/` responsibilities | Planning, inhibition, execution, modulation all belong to Phase 7+ | Phase 7 |
| All proactive behavior | Proactive talk is Phase 8 | Phase 8 |
| All `iris/event/` responsibilities | EventBus is retired for main control flow; may return for telemetry only | Post-migration |
| All `iris/kernel/plugin/` responsibilities | PluginManager eliminated entirely | Phase 9 (deletion) |
| `iris/llm/bridge.py` migration | Phase 4 already has adapter-level replacement; bridge.py is legacy orchestration | Phase 9 (deletion) |
| Legacy module deletion | All old modules remain until migration is complete | Phase 9 |

## Validation

```bash
uv run pytest tests/architecture -q
uv run ruff check .
uv run ruff format --check .
```
