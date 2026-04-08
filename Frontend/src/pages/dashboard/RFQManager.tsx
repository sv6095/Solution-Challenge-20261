import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useAddRFQThreadMessage, useCreateRFQ, useRFQs, useRFQThread, useUpdateRFQStatus } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";

const STATUS_FILTERS = ["All", "Draft", "Sent", "Responded", "Closed"];
const STATUS_OPTIONS = ["Draft", "Pending Approval", "Sent", "Responded", "Closed"] as const;

const statusColor: Record<string, string> = {
  Responded: "bg-green-500/20 text-green-500",
  Sent: "bg-blue-500/20 text-blue-400",
  Draft: "bg-surface-highest text-secondary",
  Closed: "bg-surface-highest text-secondary",
};

const RFQManager = () => {
  const [activeFilter, setActiveFilter] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [newSupplier, setNewSupplier] = useState("");
  const [newEvent, setNewEvent] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: rfqs, isLoading } = useRFQs(activeFilter !== "All" ? activeFilter : undefined);
  const createRFQ = useCreateRFQ();
  const updateStatus = useUpdateRFQStatus();
  const selected = useMemo(() => rfqs?.find((r) => r.id === selectedId) ?? null, [rfqs, selectedId]);
  const { data: thread } = useRFQThread(selected?.id);
  const addMessage = useAddRFQThreadMessage();
  const [newMsg, setNewMsg] = useState("");
  const [newMsgDir, setNewMsgDir] = useState<"note" | "inbound" | "outbound">("note");

  const handleCreate = () => {
    if (!newSupplier || !newEvent) return;
    createRFQ.mutate(
      { supplier: newSupplier, eventTrigger: newEvent, status: "Draft" },
      {
        onSuccess: () => {
          setShowForm(false);
          setNewSupplier("");
          setNewEvent("");
        },
      }
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">RFQ Management Hub</h1>
          <p className="text-body-md text-secondary mt-1">Automated sourcing requests and supplier response tracking.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="bg-sentinel text-background px-4 py-2 rounded-sm font-medium hover:opacity-90 transition-opacity"
        >
          {showForm ? "Cancel" : "+ New RFQ"}
        </button>
      </div>

      {showForm && (
        <div className="surface-container-high rounded-lg p-6 mb-6 space-y-4 max-w-md">
          <h3 className="font-headline font-bold text-sm uppercase tracking-widest">New RFQ</h3>
          <div>
            <label htmlFor="rfq-supplier" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Supplier</label>
            <input
              id="rfq-supplier"
              placeholder="Supplier name"
              value={newSupplier}
              onChange={(e) => setNewSupplier(e.target.value)}
              className="input-sentinel w-full px-4 py-3 rounded-sm"
            />
          </div>
          <div>
            <label htmlFor="rfq-event" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Event Trigger</label>
            <input
              id="rfq-event"
              placeholder="Triggering event"
              value={newEvent}
              onChange={(e) => setNewEvent(e.target.value)}
              className="input-sentinel w-full px-4 py-3 rounded-sm"
            />
          </div>
          <button
            onClick={handleCreate}
            disabled={!newSupplier || !newEvent || createRFQ.isPending}
            className="w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {createRFQ.isPending ? <><Loader2 size={16} className="animate-spin" /> Creating…</> : "Create RFQ"}
          </button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-2 mb-6">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setActiveFilter(f)}
            className={`px-4 py-2 rounded-sm text-body-md ${f === activeFilter ? "bg-sentinel text-background" : "glass-panel text-secondary hover:bg-white/10"} transition-colors`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="surface-container-high rounded-lg p-6">
        <div className="grid grid-cols-7 gap-2 text-label-sm text-secondary uppercase tracking-widest mb-4 px-2">
          <span>RFQ ID</span>
          <span>Supplier</span>
          <span>Event Trigger</span>
          <span>Date Sent</span>
          <span>Status</span>
          <span>Workflow</span>
          <span>Actions</span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-secondary" /></div>
        ) : rfqs?.length === 0 ? (
          <p className="text-body-md text-secondary text-center py-12">No RFQs found.</p>
        ) : (
          rfqs?.map((r) => (
            <div key={r.id} className="grid grid-cols-7 gap-2 items-center px-2 py-4 hover:bg-surface-highest/30 rounded-sm transition-colors">
              <span className="font-headline font-bold text-sm">{r.id}</span>
              <span className="text-body-md">{r.supplier}</span>
              <span className="text-body-md text-secondary">{r.eventTrigger}</span>
              <span className="text-body-md text-secondary">{r.dateSent}</span>
              <span className={`text-label-sm px-2 py-1 rounded-sm text-center font-bold ${statusColor[r.status] ?? "text-secondary"}`}>{r.status}</span>
              <span className="text-label-sm text-secondary">{r.workflowId ?? "—"}</span>
              <button
                className="text-sentinel text-body-md hover:underline text-left"
                onClick={() => setSelectedId(r.id)}
              >
                View Details
              </button>
            </div>
          ))
        )}
      </div>

      {selected ? (
        <div className="surface-container-high rounded-lg p-6 mt-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-headline font-bold text-lg">RFQ detail</h2>
            {selected.workflowId ? (
              <a
                href={api.workflows.reportPdfUrl(selected.workflowId)}
                target="_blank"
                rel="noopener noreferrer"
                className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors"
              >
                Open linked audit PDF
              </a>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Supplier</p>
              <p className="text-body-md">{selected.supplier}</p>
            </div>
            <div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Status</p>
              <div className="flex items-center gap-2">
                <select
                  value={selected.status}
                  onChange={(e) => updateStatus.mutate({ id: selected.id, status: e.target.value })}
                  className="input-sentinel px-3 py-2 rounded-sm bg-surface"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {updateStatus.isPending ? <Loader2 size={16} className="animate-spin text-secondary" /> : null}
              </div>
            </div>
            <div className="col-span-2">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Subject</p>
              <p className="text-body-md">{selected.eventTrigger}</p>
            </div>
            <div className="col-span-2">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Body</p>
              <pre className="whitespace-pre-wrap text-body-md text-secondary surface-container rounded-lg p-4">{selected.body ?? ""}</pre>
            </div>
            <div className="col-span-2">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Thread</p>
              <div className="surface-container rounded-lg p-4 space-y-3 mt-2">
                {(thread?.messages ?? []).length === 0 ? (
                  <p className="text-body-md text-secondary">No messages yet. Add notes or simulate supplier replies here.</p>
                ) : (
                  thread?.messages.map((m) => (
                    <div key={m.id} className="surface-container-highest rounded-lg p-3">
                      <div className="flex items-center justify-between text-label-sm text-secondary">
                        <span className="uppercase tracking-widest">{m.direction}</span>
                        <span>{new Date(m.created_at).toLocaleString()}</span>
                      </div>
                      <p className="text-body-md text-secondary mt-2 whitespace-pre-wrap">{m.body}</p>
                    </div>
                  ))
                )}
                <div className="grid grid-cols-[160px_1fr_140px] gap-2">
                  <select value={newMsgDir} onChange={(e) => setNewMsgDir(e.target.value as any)} className="input-sentinel px-3 py-2 rounded-sm bg-surface">
                    <option value="note">note</option>
                    <option value="outbound">outbound</option>
                    <option value="inbound">inbound</option>
                  </select>
                  <input value={newMsg} onChange={(e) => setNewMsg(e.target.value)} className="input-sentinel px-3 py-2 rounded-sm" placeholder="Add a message…" />
                  <button
                    onClick={() => {
                      if (!selected?.id || !newMsg.trim()) return;
                      addMessage.mutate({ id: selected.id, direction: newMsgDir, body: newMsg.trim() });
                      setNewMsg("");
                    }}
                    className="bg-foreground text-background rounded-sm px-3 py-2 hover:opacity-90 transition-opacity"
                  >
                    Add
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default RFQManager;
