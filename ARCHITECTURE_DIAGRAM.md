# Griptape Nodes Architecture Diagram

## Manager Dependency Architecture

```mermaid
graph TB
    %% Application Layer
    App[FastAPI App<br/>app.py]
    WS[WebSocket Manager<br/>NodesApiSocketManager]

    %% Singleton Container
    GN[GriptapeNodes Singleton<br/>griptape_nodes.py]

    %% Core Hub
    EM[EventManager<br/>No Dependencies]

    %% Configuration Layer
    CM[ConfigManager<br/>→ EventManager]
    SM[SecretsManager<br/>→ ConfigManager<br/>→ EventManager]
    OPM[OperationDepthManager<br/>→ ConfigManager]

    %% Storage & Files Layer
    SFM[StaticFilesManager<br/>→ ConfigManager<br/>→ SecretsManager<br/>→ EventManager]

    %% Core Execution Managers
    OM[ObjectManager<br/>→ EventManager]
    NM[NodeManager<br/>→ EventManager]
    FM[FlowManager<br/>→ EventManager]
    CTX[ContextManager<br/>→ EventManager]

    %% Library & Workflow Layer
    LM[LibraryManager<br/>→ EventManager]
    WFM[WorkflowManager<br/>→ EventManager]
    VCM[VersionCompatibilityManager<br/>→ EventManager]

    %% Execution Support
    VM[VariablesManager<br/>→ EventManager]
    ACM[ArbitraryCodeExecManager<br/>→ EventManager]
    MM[ModelManager<br/>→ EventManager]
    AGM[AgentManager<br/>→ StaticFilesManager<br/>→ EventManager]

    %% Infrastructure
    OSM[OSManager<br/>→ EventManager]
    RM[ResourceManager<br/>→ EventManager]

    %% Identity & Session
    EIM[EngineIdentityManager<br/>→ EventManager]
    SSM[SessionManager<br/>→ EngineIdentityManager<br/>→ EventManager]
    UM[UserManager<br/>→ SecretsManager]

    %% Cloud & Sync
    MCPM[MCPManager<br/>→ EventManager<br/>→ ConfigManager]
    SYM[SyncManager<br/>→ EventManager<br/>→ ConfigManager]
    PM[ProjectManager<br/>→ EventManager<br/>→ ConfigManager<br/>→ SecretsManager]

    %% Application connections
    App --> GN
    App --> WS
    WS --> EM

    %% Singleton contains all managers
    GN -.contains.-> EM
    GN -.contains.-> CM
    GN -.contains.-> SM
    GN -.contains.-> OPM
    GN -.contains.-> SFM
    GN -.contains.-> OM
    GN -.contains.-> NM
    GN -.contains.-> FM
    GN -.contains.-> CTX
    GN -.contains.-> LM
    GN -.contains.-> WFM
    GN -.contains.-> VCM
    GN -.contains.-> VM
    GN -.contains.-> ACM
    GN -.contains.-> MM
    GN -.contains.-> AGM
    GN -.contains.-> OSM
    GN -.contains.-> RM
    GN -.contains.-> EIM
    GN -.contains.-> SSM
    GN -.contains.-> UM
    GN -.contains.-> MCPM
    GN -.contains.-> SYM
    GN -.contains.-> PM

    %% Constructor dependencies (solid lines)
    CM --> EM
    SM --> CM
    SM --> EM
    OPM --> CM
    SFM --> CM
    SFM --> SM
    SFM --> EM
    AGM --> SFM
    AGM --> EM
    SSM --> EIM
    SSM --> EM
    UM --> SM
    MCPM --> EM
    MCPM --> CM
    SYM --> EM
    SYM --> CM
    PM --> EM
    PM --> CM
    PM --> SM

    %% All basic managers depend on EventManager
    OM --> EM
    NM --> EM
    FM --> EM
    CTX --> EM
    LM --> EM
    WFM --> EM
    VCM --> EM
    VM --> EM
    ACM --> EM
    MM --> EM
    OSM --> EM
    RM --> EM
    EIM --> EM

    style GN fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px
    style EM fill:#4dabf7,stroke:#1971c2,stroke-width:3px
    style App fill:#51cf66,stroke:#2f9e44,stroke-width:2px
    style FM fill:#ffd43b,stroke:#f59f00,stroke-width:2px
    style NM fill:#ffd43b,stroke:#f59f00,stroke-width:2px
    style WFM fill:#ffd43b,stroke:#f59f00,stroke-width:2px
```

## Runtime Manager Interaction Graph

This shows how managers call each other during workflow execution (not constructor dependencies):

```mermaid
graph LR
    %% Core Execution Flow
    FM[FlowManager]
    NM[NodeManager]
    OM[ObjectManager]
    CTX[ContextManager]
    EM[EventManager]
    WFM[WorkflowManager]
    LM[LibraryManager]
    VM[VariablesManager]

    %% FlowManager runtime calls
    FM -->|get_current_flow| CTX
    FM -->|store/retrieve objects| OM
    FM -->|get_node| NM
    FM -->|workflow_shape| WFM
    FM -->|emit_events| EM

    %% NodeManager runtime calls
    NM -->|get_flow/connections| FM
    NM -->|get_context| CTX
    NM -->|register objects| OM

    %% EventManager runtime calls
    EM -->|track_depth| OPM[OperationDepthManager]
    EM -->|check_altered| WFM
    EM -->|flush_changes| OM

    %% ContextManager runtime calls
    CTX -->|get_objects| OM

    %% ObjectManager runtime calls
    OM -->|rename_flow| FM
    OM -->|rename_node| NM
    OM -->|clear_all| FM
    OM -->|clear_all| CTX
    OM -->|clear_all| VM
    OM -->|handle_request| EM

    %% VersionCompatibilityManager runtime calls
    VCM[VersionCompatibilityManager] -->|library_metadata| LM
    VCM -->|workflow_status| WFM

    %% WorkflowManager runtime calls
    WFM -->|library_ops| LM
    WFM -->|node_ops| NM
    WFM -->|flow_ops| FM
    WFM -->|config| CM[ConfigManager]
    WFM -->|context| CTX
    WFM -->|objects| OM
    WFM -->|secrets| SM[SecretsManager]

    style FM fill:#ffd43b,stroke:#f59f00,stroke-width:3px
    style NM fill:#ffd43b,stroke:#f59f00,stroke-width:3px
    style OM fill:#ff8787,stroke:#fa5252,stroke-width:2px
    style CTX fill:#ff8787,stroke:#fa5252,stroke-width:2px
    style EM fill:#4dabf7,stroke:#1971c2,stroke-width:3px
```

## Workflow Execution Flow

```mermaid
sequenceDiagram
    participant WF as Workflow File<br/>(workflow_2.py)
    participant RM as RetainedMode API
    participant GN as GriptapeNodes<br/>Singleton
    participant EM as EventManager
    participant FM as FlowManager
    participant NM as NodeManager
    participant OM as ObjectManager
    participant CTX as ContextManager
    participant CFM as ControlFlowMachine
    participant Executor as NodeExecutor

    %% Initialization
    WF->>RM: Load libraries
    RM->>GN: handle_request(LoadLibrariesRequest)
    GN->>EM: route to LibraryManager

    %% Context Setup
    WF->>RM: Get ContextManager
    RM->>GN: ContextManager()
    WF->>CTX: push_workflow_context()

    %% Flow Creation
    WF->>RM: create_flow("Main Flow")
    RM->>GN: handle_request(CreateFlowRequest)
    GN->>EM: route to FlowManager
    EM->>FM: on_create_flow_request()
    FM->>OM: register_object(flow)
    FM->>CTX: push_flow_context()

    %% Node Creation
    WF->>RM: create_node("Agent")
    RM->>GN: handle_request(CreateNodeRequest)
    GN->>EM: route to NodeManager
    EM->>NM: on_create_node_request()
    NM->>FM: get_current_flow()
    NM->>OM: register_object(node)

    %% Execution Start
    WF->>RM: run_flow("Main Flow")
    RM->>GN: handle_request(StartFlowRequest)
    GN->>EM: route to FlowManager
    EM->>FM: on_start_flow_request()
    FM->>OM: get_object_by_name(flow)
    FM->>CTX: set_current_flow()
    FM->>CFM: create ControlFlowMachine

    %% State Machine Loop
    CFM->>CFM: ResolveNodeState
    CFM->>Executor: execute_node()
    Executor->>NM: resolve inputs
    NM->>FM: get_connections()
    Executor->>Executor: node.process()
    Executor->>OM: store outputs

    CFM->>CFM: NextNodeState
    CFM->>FM: get_next_node()
    FM->>OM: get_connected_nodes()

    CFM->>CFM: CompleteState
    CFM->>EM: broadcast ControlFlowResolvedEvent
    EM->>WF: execution complete
```

## Application Startup Sequence

```mermaid
sequenceDiagram
    participant Main as __main__
    participant App as app.py
    participant GN as GriptapeNodes
    participant EM as EventManager
    participant CM as ConfigManager
    participant WS as WebSocket Thread
    participant EQ as Event Queue

    Main->>App: run()
    App->>GN: GriptapeNodes() singleton
    GN->>GN: Initialize all 23 managers

    Note over GN: Managers initialized in order:<br/>1. EventManager<br/>2. ResourceManager<br/>3. ConfigManager<br/>...<br/>23. ProjectManager

    App->>CM: access ConfigManager
    App->>App: Configure logging
    App->>App: astart_app()
    App->>EM: initialize_queue()
    EM->>EQ: create asyncio.Queue

    App->>WS: Start WebSocket thread
    WS->>WS: Connect to cloud IDE

    par Event Processing
        App->>EQ: _process_event_queue()
        EQ->>EM: handle_request()
        EM->>EM: route to manager
    and WebSocket Incoming
        WS->>EQ: _process_incoming_messages()
        EQ->>EQ: add to queue
    and WebSocket Outgoing
        WS->>WS: _send_outgoing_messages()
        WS->>WS: send to cloud
    end

    App->>EM: broadcast AppInitializationComplete
    EM->>EM: trigger library loading
```

## Manager Initialization Order

```mermaid
graph TD
    Start[Application Start] --> GN[GriptapeNodes Singleton Created]

    GN --> L1[Layer 1: Core Hub]
    L1 --> EM[EventManager]

    EM --> L2[Layer 2: Configuration]
    L2 --> CM[ConfigManager]
    L2 --> OSM[OSManager]
    L2 --> RM[ResourceManager]

    CM --> L3[Layer 3: Secrets & Depth]
    L3 --> SM[SecretsManager]
    L3 --> OPM[OperationDepthManager]

    SM --> L4[Layer 4: Storage]
    L4 --> SFM[StaticFilesManager]

    EM --> L5[Layer 5: Core Execution]
    L5 --> OM[ObjectManager]
    L5 --> NM[NodeManager]
    L5 --> FM[FlowManager]
    L5 --> CTX[ContextManager]

    EM --> L6[Layer 6: Libraries & Workflows]
    L6 --> LM[LibraryManager]
    L6 --> WFM[WorkflowManager]
    L6 --> VCM[VersionCompatibilityManager]

    EM --> L7[Layer 7: Execution Support]
    L7 --> VM[VariablesManager]
    L7 --> ACM[ArbitraryCodeExecManager]
    L7 --> MM[ModelManager]

    SFM --> L8[Layer 8: Advanced Features]
    L8 --> AGM[AgentManager]

    EM --> L9[Layer 9: Identity]
    L9 --> EIM[EngineIdentityManager]

    EIM --> L10[Layer 10: Session]
    L10 --> SSM[SessionManager]

    SM --> L11[Layer 11: User]
    L11 --> UM[UserManager]

    CM --> L12[Layer 12: Cloud Services]
    EM --> L12
    L12 --> MCPM[MCPManager]
    L12 --> SYM[SyncManager]

    CM --> L13[Layer 13: Projects]
    SM --> L13
    EM --> L13
    L13 --> PM[ProjectManager]

    style GN fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px
    style EM fill:#4dabf7,stroke:#1971c2,stroke-width:3px
    style FM fill:#ffd43b,stroke:#f59f00,stroke-width:2px
    style NM fill:#ffd43b,stroke:#f59f00,stroke-width:2px
```

## Key Architectural Patterns

### 1. Singleton Container Pattern
- **GriptapeNodes** contains all managers as singleton instances
- Lazy initialization on first access
- Global state shared across entire application

### 2. Event-Driven Hub-and-Spoke
- **EventManager** at the center
- All operations flow through request/response events
- Managers register handlers for specific event types

### 3. Context Hierarchy
- **ContextManager** maintains: Workflow → Flow → Node → Element
- Provides scope for operations
- Tracks current execution context

### 4. Object Registry Pattern
- **ObjectManager** maintains name-to-object mapping
- All flows, nodes, and parameters registered globally
- Name collisions prevented by registry

### 5. State Machine Execution
- **ControlFlowMachine** orchestrates execution
- States: ResolveNodeState → NextNodeState → CompleteState
- Isolated or global DAG builder based on context

## Critical Coupling Points

### Tightly Coupled (Prevents Isolation)
1. **GriptapeNodes Singleton** - Only one instance globally
2. **FlowManager Global State** - Single control flow machine, queue, DAG
3. **ObjectManager Global Registry** - All objects in one namespace
4. **Cross-Manager Singleton Access** - `GriptapeNodes.ManagerName()` everywhere

### Loosely Coupled (Enables Flexibility)
1. **Library System** - Plugin architecture
2. **Storage Backends** - Strategy pattern
3. **Event Handlers** - Registration-based routing
4. **Node Types** - Inheritance with minimal interface

## Files Referenced

### Core Files
- [griptape_nodes.py](src/griptape_nodes/retained_mode/griptape_nodes.py) - Singleton container
- [app.py](src/griptape_nodes/app/app.py) - Application entry point
- [event_manager.py](src/griptape_nodes/retained_mode/managers/event_manager.py) - Event routing hub

### Execution Files
- [flow_manager.py](src/griptape_nodes/retained_mode/managers/flow_manager.py) - Flow lifecycle
- [node_manager.py](src/griptape_nodes/retained_mode/managers/node_manager.py) - Node operations
- [control_flow.py](src/griptape_nodes/machines/control_flow.py) - State machine
- [node_executor.py](src/griptape_nodes/common/node_executor.py) - Node execution

### Support Files
- [object_manager.py](src/griptape_nodes/retained_mode/managers/object_manager.py) - Object registry
- [context_manager.py](src/griptape_nodes/retained_mode/managers/context_manager.py) - Context stack
- [workflow_manager.py](src/griptape_nodes/retained_mode/managers/workflow_manager.py) - Workflow persistence
- [library_registry.py](src/griptape_nodes/node_library/library_registry.py) - Library management

### Example Workflow
- [workflow_2.py](GriptapeNodes/workflow_2.py) - Example workflow file
