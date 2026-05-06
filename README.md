# Praecantator: Autonomous AI-Driven Supply Chain Risk Management (SCRM)

**Praecantator** is an enterprise-grade, autonomous platform designed to continuously monitor global supply chain networks, predict cascading disruption risks using Graph Neural Networks (GNNs), and autonomously orchestrate mitigation strategies (such as optimal rerouting and backup supplier engagement) via an advanced multi-agent system.

By transitioning from static, backward-looking dashboards to proactive, forward-looking AI workflows, Praecantator acts as the "Palantir for Supply Chains," enabling users to make complex logistical decisions in real-time, fortified by human-in-the-loop governance and robust multi-tenant data isolation.

---

## 🏗 System Architecture Overview

The platform uses a decoupled frontend and backend architecture to handle high-velocity signal ingestion, complex risk computing, and highly responsive user interfaces.

### 1. Frontend Interface (`/Frontend`)
Built with React, Vite, and TypeScript, the Frontend provides a tactical command center for supply chain operations. It includes:
* **Orchestration Dashboard & Incidents View:** A real-time timeline visualizing AI reasoning pipelines (`DETECT -> ASSESS -> DECIDE -> ACT -> AUDIT`). High-risk events display a "Governance Checkpoint" banner requiring manual human approval for logistical changes.
* **Network & Global Intelligence View:** 3D rendered spatial maps utilizing OpenStreetMap map tiles. It allows users to visualize global suppliers, monitor spatial risk polygons, and view heatmaps driven by global indices.
* **Componentry & State:** Designed with modularity using `framer-motion` for fluid transitions and `@tanstack/react-query` to maintain a globally synchronized state matching the fast-paced backend telemetry.

### 2. Backend Engine (`/Backend`)
The Python-powered FastAPI backend relies on heavily optimized multi-agent workflows (powered by LangGraph) seamlessly interacting with PyTorch Geometric data structures and Firestore-backed event storage.
* **Multi-Agent Orchestrator:** Agents run sequentially (Signal -> Assessment -> Routing -> RFQ/Audit), simulating OODA loop command execution.
* **Graph Intelligence:** Replaces tabular row structures with dynamic network simulations. Local supplier nodes are evaluated alongside global catastrophic events dynamically mapping radial impact zones utilizing advanced isolated Spatial/Bounding Box optimizations to prevent runtime memory exhaustion.
* **Enterprise Security & Tenancy:** Strict Role-Based Access Control (RBAC). A central policy engine segregates datasets ensuring a zero-trust model where data bleed between clients is completely eliminated, whilst allowing safe cross-tenant intelligence utilizing strict DUNS/LEI entity resolution intersections.

---

## 🚀 Key Features

### 🌟 Autonomous Workflow Engine
Unlike traditional systems that alert operators linearly, Praecantator utilizes a multi-step LangGraph autonomous pipeline. Signals ingested through various global intelligence nodes (GDELT, NASA EONET, etc.) automatically trigger the pipeline.
* **Detection:** Cross-referencing real world perturbations with internal `CustomerSupplyGraph` metrics.
* **Analysis:** Determining blast radiuses, downtime likelihood, and cost implications.
* **Decision Synthesis:** Executing routing simulations targeting cost optimization paired with the lowest delay profiles.
* **Action & Audit:** Generating actual Request-For-Quotes (RFQs), notifying endpoints, and permanently logging the exact ledger of reasoning.

### 🛡️ Deep Enterprise Governance & Supply Constraints
All external actions require stringent transparency and mirror physical operational truths.
* **Bill-Of-Materials (BOM) Granularity:** The pipeline understands distinct product characteristics. Temporary delays in general manufacturing reroute standard cargo, but perishable logistics natively calculate total loss vectors automatically overriding simplistic AI suggestions.
* **ERP Live Hydration:** Risk calculations discard static safety stock parameters during routing loops, fetching dynamic throughput rates globally prior to executing graph traversal evaluations.
* **Pending Checkpoints:** High-risk actions halt the `ACT` stage until explicit operations manager sign-off.
* **Idempotency Guardrails:** The platform safely catches orchestration failures, allowing users to safely attempt pipeline restarts natively without triggering duplicated side effects or duplicated quote emails.
* **Audit Traces:** Every algorithmic jump a mathematical calculation or LLM makes is appended via `reasoning_steps`, visible directly on the React frontend.

---

## 🛠️ Getting Started & Local Development

**Production (Firebase, Render, Vercel, Google sign-in):** step-by-step checklist → [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md). Detailed deploy and troubleshooting → [`docs/DEPLOYMENT_FIREBASE.md`](docs/DEPLOYMENT_FIREBASE.md).

### Prerequisites
* Python 3.11+ (see `Backend/.python-version`; required for current dependency pins)
* Node.js v18+ (npm or vpm)

### Launching the Backend
1. Navigate to the `Backend` directory:
   ```bash
   cd Backend
   ```
2. Setup your virtual environment: 
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI development server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Launching the Frontend
1. Keep the backend running, open a new terminal, and navigate to the `Frontend` directory:
   ```bash
   cd Frontend
   ```
2. Install necessary node modules:
   ```bash
   npm install
   ```
3. Boot the Vite server:
   ```bash
   npm run dev
   ```

You are ready to command Praecantator. Open `http://localhost:5173` to log in and observe autonomous risk modeling.

---
_Documentation automatically generated for Praecantator System v4.0_
