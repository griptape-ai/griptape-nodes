# Griptape Framework Glossary for Computer Artists

## What is Griptape?

**Griptape** is a creative toolkit (built with Python programming language) that helps artists and creators build AI-powered projects without needing deep technical expertise. Think of it like a set of building blocks that you can connect together to create interactive art, generate images, process text, or build other creative applications.

## Building Blocks of Griptape

### The Basics

**Workflow**: A saved document containing nodes, connections, and values.  While technically a Workflow is also a Script, we should avoid calling them Scripts, so that the term Script can communicate a clearly different thing than the term Workflow.
**Workflow Editor**: The workspace where nodes are added, connected, and configured.
**Flow**: A collection of connected nodes that form a functional unit. A Workflow can contain 0-n Flows.
**Sub-Flow**: A contained set of nodes that executes within a Loop, Branch, Reference (and sometimes Groups). This refers to any logically distinct, internally-contained portion of a flow that functions as a cohesive unit.
**Reference**: A link to another Flow, embedding it as a Sub-Flow within the current context.
**Group**: A visual clustering of nodes. A Group may act as a Sub-Flow if it is executed as a unit, but grouping alone does not imply execution and may simply be a subjectively related set of nodes.
**Script**: A Python script that runs code. This term should be avoided when describing a Workflow; instead, script refers to tools, macros, or flow-building aids.
**Libraries**: Collections of node definitions and/or scripts that extend functionality


- **Node**: A single piece of the puzzle in your creative project. Nodes are like LEGO blocks that you can connect to create something bigger. Each node does one specific thing (like generating an image or processing text).
  - **DataNode**: A node that handles information — it can transform data from one form to another.
  - **ControlNode**: A node that makes decisions in your project, like "if this happens, do that."
  - **DriverNode**: A node that connects your project to outside services (like image generators or search engines).
  - **ParameterNode**: A simple node that just holds a specific setting or value.

- **Tool**: A ready-to-use component that performs a specific function. Tools are like brushes in your digital toolkit — each designed for a specific purpose.
  - **CalculatorTool**: Does math calculations for you.
  - **DateTimeTool**: Works with dates and times.
  - **FileManagerTool**: Helps manage files (saving, loading, etc.).
  - **WebScraperTool**: Collects information from websites.
  - **PromptSummaryTool**: Creates summaries of longer text.

- **Driver**: The connector between your project and external AI services or databases. Drivers are like adapters that let your project talk to specialized services.
  - **PromptDriver**: Communicates with AI text generators (like GPT models).
  - **WebSearchDriver**: Connects to search engines to find information.
  - **EmbeddingDriver**: Transforms words and concepts into numerical form that AI can understand.
  - **ImageGenerationDriver**: Connects to AI image generators (like DALL-E).
  - **AudioTranscriptionDriver**: Converts spoken audio to written text.

- **Engine**: The powerhouse that processes your creative requests. Engines are specialized components that transform inputs into creative outputs.
  - **RagEngine**: Processes questions and generates answers based on provided information.
  - **PromptSummaryEngine**: Creates concise summaries of longer text.
  - **CsvExtractionEngine**: Pulls information from spreadsheet-like files.
  - **JsonExtractionEngine**: Pulls information from structured data files.

- **Artifact**: A piece of content created during your project, like a generated image or text. Artifacts are the outputs of your creative process.
  - **ErrorArtifact**: A notification when something goes wrong.

- **Agent**: A helper that can perform tasks on your behalf, often using a combination of tools. Agents are like assistants that can navigate a sequence of operations for you.

- **Ruleset**: A set of guidelines that control how your project behaves. Rulesets are like recipes that tell your project how to respond in different situations.
  - **Rule**: A single instruction within a ruleset, like "if the user asks for an image, generate one."

### Settings and Configuration

- **Parameter**: A setting or value you can adjust in your project. Parameters are like the knobs and sliders in a music synthesizer — they let you fine-tune how things work.
  - **ParameterMode**: Determines if a parameter is for input, output, or both.
  - **ParameterValues**: A collection of all current settings.
  - **ParameterOutputValues**: The results produced by your parameters.
  - **ParameterUIOptions**: Settings for how parameters appear in the user interface.
  - **NumberTypeOptions**: Options for number parameters (like minimum/maximum values).
  - **StringTypeOptions**: Options for text parameters (like allowing multiple lines).

- **Dictionary**: A way to store information as pairs of labels and values. Dictionaries are like organized containers where each item has a unique label.
  - **Key-value pair**: A label (key) paired with its corresponding information (value).
  - **SparseDictionary**: A more efficient dictionary that only stores necessary information.

- **Graph-Based Architecture**: The overall design approach where different components (nodes) connect to each other to create a workflow. This is like how you might arrange physical equipment in a studio, connecting different devices to create a signal chain.

## Technical Terms Made Simple

- **API Key**: A special password that grants your project access to external services like AI image generators. Think of it like a membership card that lets you use specific online services.
  - **API Key Environment Variable**: A secure place to store your API key.

- **AST (Abstract Syntax Tree)**: A way computers understand the structure of code. This is like the grammar rules of programming languages.
  - **ast.literal_eval**: A function that safely interprets simple written expressions.

- **Connection**: The link that allows nodes to communicate with each other. Connections are like the cables connecting different pieces of equipment.

- **Default Value**: The pre-set value a parameter has before you change it. This is like the factory settings on a device.

- **Parameter Validation**: A check that ensures the values you enter make sense. This prevents errors like trying to use text where a number is needed.

- **Off-prompt mode**: A setting where tools work automatically without asking for additional input.

- **Stream Mode**: A continuous processing mode, like a live video feed rather than taking separate photos.

- **Temperature Control**: A setting that controls how creative or predictable an AI's responses will be. Lower temperature means more predictable, higher temperature means more creative and varied.

## AI Terms for Artists

- **Embedding Model**: An AI tool that converts words, images, or other content into numbers that capture their meaning. This helps AI understand relationships between different concepts.

- **GPT Models**: AI systems that can generate human-like text based on the input they receive.
  - **GPT-4o**: A specific version of GPT with enhanced capabilities.

- **NLP (Natural Language Processing)**: The field of AI focused on helping computers understand and generate human language.

- **Prompt**: The input text you provide to guide an AI model. For artists, this is similar to a creative brief or instructions to a collaborator.

- **Response Format**: The type of output you receive from an AI (like plain text, formatted text, or structured data).

- **Text Summarization**: The process of condensing longer text into shorter, essential versions.

- **Vector Store**: A specialized database that stores information in a way that captures relationships and meaning, not just the information itself.

## AI Services for Creative Projects

### Anthropic

- **Anthropic API**: A service providing advanced AI text generation capabilities (Claude).

### Azure OpenAI

- **Azure Deployment**: Microsoft's version of OpenAI services (like GPT and DALL-E).
- **Azure Deployment Name**: The name of your specific setup within Azure.
- **Azure Endpoint**: The connection point to access Azure AI services.

### Cohere

- **Cohere**: A text generation service with specialized features for different creative applications.

### DuckDuckGo

- **DuckDuckGoWebSearchDriver**: A component that lets your project search the web using DuckDuckGo.

### DALL-E

- **DALL-E Model**: An AI system that creates images based on text descriptions.
- **DALL-E 2 & 3**: Different versions of the DALL-E image generator, with version 3 being more advanced.

### Ollama

- **Ollama**: A service that helps integrate AI models into your applications.
- **Ollama Prompt Driver**: A component that connects to Ollama's text generation capabilities.

## Helpful Programming Concepts

- **Callback**: A function that automatically runs when something specific happens. This is like setting up a camera to take a photo when motion is detected.

- **Custom Parameter Types**: Specialized settings you can define for your specific project needs.

- **Exception Handling**: The way your project deals with errors. This is like having backup plans for when things go wrong.
  - **Authentication Error**: An error that occurs when your project can't prove it has permission to use a service.
  - **KeyError**: An error when your project tries to access information using an incorrect label.
  - **SyntaxError**: An error caused by incorrect formatting in code.
  - **ValueError**: An error when your project tries to use an inappropriate value.

- **Lifecycle Management**: How your project handles creating, using, and closing components. This is like the startup and shutdown procedures for complex equipment.

- **Metadata**: Extra information about your content or components. This is like the information stored in digital photo files (camera type, date taken, etc.).

- **Node Extension**: Adding new features to existing nodes. This is like adding effects pedals to a guitar setup.

- **Node Validation**: Checking if a node is properly set up before running it. This is like testing equipment before a performance.

- **Parameter Interpolation**: Blending or calculating values from multiple sources to create a new value. This is similar to color mixing in visual art.

## Additional Terms

- **Python**: A popular programming language that Griptape is built with. Python is known for being relatively easy to read and understand compared to other programming languages.

- **API (Application Programming Interface)**: A set of rules that allows different software applications to communicate with each other. For artists, this is like the standardized connections that allow different audio equipment to work together.

- **JSON (JavaScript Object Notation)**: A common format for storing and transmitting data. This is like a standardized template for organizing information.

- **CSV (Comma-Separated Values)**: A simple file format used to store tabular data, such as spreadsheet data. Each line represents a row, and commas separate the values in each column.

- **UI (User Interface)**: The visual elements and controls that allow humans to interact with software. This includes buttons, sliders, text fields, and other interactive elements.

- **Workflow**: A sequence of connected steps to accomplish a task. In Griptape, workflows are created by connecting nodes together to create more complex functionality.

- **Framework**: A pre-built set of code that provides structure and functionality to build applications more easily. Frameworks are like art supply kits that come with the basic materials and tools you need.

- **Type Hints**: Labels that suggest what kind of information a parameter expects. These are like labels on art supply containers telling you what's inside.
  - **Any**: A type hint meaning a parameter can accept any kind of information.
  - **List**: A type hint for a collection of items (like an array of colors or shapes).
  - **Literal**: A type hint indicating a parameter only accepts specific preset values.
  - **Union type**: A type hint showing a parameter can accept multiple specific types of information.