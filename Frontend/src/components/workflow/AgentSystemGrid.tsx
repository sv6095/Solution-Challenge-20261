'use client'

import React, { useState, useEffect, useRef } from 'react'
import { motion, useMotionValue, useSpring } from 'motion/react'
import { 
  User, 
  Radio, 
  ClipboardList, 
  GitBranch, 
  Globe, 
  Banknote, 
  Truck, 
  FileEdit, 
  Headset,
  Activity
} from 'lucide-react'
import { SplineScene } from '@/components/ui/splite'
import { cn } from '@/lib/utils'
import type { AgentChatResult } from "@/types/workflow";

type Props = {
  result?: AgentChatResult | null;
  loading?: boolean;
  onQuickRun?: (prompt: string) => void | Promise<void>;
};

interface NodeProps {
  label: string
  status: "Idle" | "Running" | "Completed" | "Failed"
  icon: React.ReactNode
  position: { top: string; left?: string; right?: string }
  align: 'left' | 'right'
  active?: boolean
  onClick?: (e: React.MouseEvent) => void
  key?: React.Key
}

/* ── Clean circular node — no outer ring, no glow ── */
const NodeCircle = ({ icon, active }: { icon: React.ReactNode; active?: boolean }) => (
  <div
    className={cn(
      "w-8 h-8 rounded-full border flex items-center justify-center bg-black transition-colors duration-150",
      active ? "border-[#DC2626]" : "border-[#333] group-hover:border-[#DC2626]"
    )}
  >
    {React.cloneElement(icon as React.ReactElement, { 
      className: cn("w-3.5 h-3.5", active ? "text-[#DC2626]" : "text-white/80 group-hover:text-[#EF4444]") 
    })}
  </div>
)

/* ── Status label with semantic meaning ── */
const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  Idle:      { text: "Standby",   color: "text-[#555]" },
  Running:   { text: "Active",    color: "text-[#DC2626]" },
  Completed: { text: "Done",      color: "text-white" },
  Failed:    { text: "Error",     color: "text-[#EF4444]" },
}

const Node = ({ label, status, icon, position, align, active, onClick }: NodeProps) => {
  const statusInfo = STATUS_LABELS[status] ?? STATUS_LABELS.Idle;
  return (
    <motion.div 
      className={cn(
        "absolute z-30 cursor-pointer group flex items-center gap-3",
        align === 'left' ? "flex-row-reverse" : "flex-row"
      )}
      style={position}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      whileHover={{ scale: 1.05 }}
      transition={{ duration: 0.15 }}
      onClick={onClick}
    >
      <div className={cn(
        "flex flex-col",
        align === 'left' ? "text-right" : "text-left"
      )}>
        <span className="text-white font-bold text-[11px] tracking-tight leading-none uppercase">{label}</span>
        <span className={`text-[9px] font-medium mt-0.5 ${statusInfo.color}`}>{statusInfo.text}</span>
      </div>

      <NodeCircle icon={icon} active={active} />
    </motion.div>
  )
}

export function AgentSystemGrid({ result, loading = false, onQuickRun }: Props) {
  const [activeNode, setActiveNode] = useState<string | null>(null)
  
  const sequence = new Set((result?.sequence ?? []).map((item) => String(item)));
  const outputKeys = new Set(Object.keys(result?.outputs ?? {}));
  const backendStatuses = (result?.outputs?.agent_statuses ?? {}) as Record<string, "Idle" | "Running" | "Completed" | "Failed">;

  const [commandActive, setCommandActive] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Parallax values
  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  const springX = useSpring(mouseX, { stiffness: 40, damping: 15 })
  const springY = useSpring(mouseY, { stiffness: 40, damping: 15 })

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return
      const { width, height, left, top } = containerRef.current.getBoundingClientRect()
      const x = (e.clientX - left - width / 2) / 40
      const y = (e.clientY - top - height / 2) / 40
      mouseX.set(x)
      mouseY.set(y)
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [mouseX, mouseY])

  const handleNodeClick = (id: string, prompt: string) => {
    setActiveNode(id === activeNode ? null : id)
    if (onQuickRun) {
      onQuickRun(prompt);
    }
  }

  const handleCommandClick = () => {
    setCommandActive(true)
    if (onQuickRun) {
      onQuickRun("Coordinate all specialist agents and give me the best response path for this disruption.");
    }
    setTimeout(() => setCommandActive(false), 2000);
  }

  const leftNodes = [
    { id: 'supervisor', label: 'SUPERVISOR', prompt: 'Coordinate all specialist agents and give me the best response path for this disruption.', icon: <User />, position: { top: '22%', left: '22%' } },
    { id: 'signal_agent', label: 'SIGNAL', prompt: 'Review the current disruption signals and explain which one matters most right now.', icon: <Radio />, position: { top: '38%', left: '25%' } },
    { id: 'assessment_agent', label: 'ASSESSMENT', prompt: 'Assess supplier exposure, financial impact, and time at risk for this disruption.', icon: <ClipboardList />, position: { top: '54%', left: '25%' } },
    { id: 'routing_agent', label: 'ROUTING', prompt: 'Compare sea, air, and land responses and recommend the best routing path.', icon: <GitBranch />, position: { top: '70%', left: '22%' } },
  ]

  const rightNodes = [
    { id: 'political_risk_agent', label: 'POLITICAL', prompt: 'Give me the political and geopolitical risk picture for this workflow.', icon: <Globe />, position: { top: '16%', right: '22%' } },
    { id: 'tariff_risk_agent', label: 'TARIFF', prompt: 'Analyze tariff and customs risk for the affected suppliers and routes.', icon: <Banknote />, position: { top: '32%', right: '25%' } },
    { id: 'logistics_risk_agent', label: 'LOGISTICS', prompt: 'Analyze logistics execution risk, route bottlenecks, and fallback transport constraints.', icon: <Truck />, position: { top: '48%', right: '27%' } },
    { id: 'reporting_agent', label: 'REPORTING', prompt: 'Create a full consolidated report for leadership and compliance review.', icon: <FileEdit />, position: { top: '64%', right: '25%' } },
    { id: 'assistant_agent', label: 'ASSISTANT', prompt: 'Summarize the current workflow in plain English and tell me what to do next.', icon: <Headset />, position: { top: '80%', right: '22%' } },
  ]

  const getStatus = (id: string): "Idle" | "Running" | "Completed" | "Failed" => {
    const fromBackend = backendStatuses[id];
    if (fromBackend) return fromBackend;
    if (loading && (activeNode === id || sequence.has(id))) return "Running";
    if (outputKeys.has(id) || sequence.has(id)) return "Completed";
    return "Idle";
  }
  const isActive = (id: string) => getStatus(id) === "Running";

  const isAnyActive = loading || commandActive;

  return (
    <div ref={containerRef} className="relative w-full h-[600px] lg:h-[700px] bg-black overflow-hidden font-sans selection:bg-[#DC2626]/30 rounded-sm border border-[#222]">
      {/* Background Grid Pattern — subtle */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:100px_100px]" />

      {/* Main Content Container */}
      <div className="relative h-full flex items-center justify-center max-w-[1800px] mx-auto">
        
        {/* 3D Robot Scene with Parallax — KEPT as centerpiece */}
        <motion.div 
          className="absolute inset-0 z-10 flex items-center justify-center"
          style={{ x: springX, y: springY }}
        >
          <div className="relative w-full h-full max-w-4xl">
            <SplineScene 
              scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
              className="w-full h-full"
            />
          </div>
        </motion.div>

        {/* Left Nodes */}
        {leftNodes.map((node, i) => (
          <Node 
            key={`left-${i}`}
            label={node.label}
            status={getStatus(node.id)}
            icon={node.icon}
            position={node.position}
            align="left"
            active={isActive(node.id)}
            onClick={() => handleNodeClick(node.id, node.prompt)}
          />
        ))}

        {/* Right Nodes */}
        {rightNodes.map((node, i) => (
          <Node 
            key={`right-${i}`}
            label={node.label}
            status={getStatus(node.id)}
            icon={node.icon}
            position={node.position}
            align="right"
            active={isActive(node.id)}
            onClick={() => handleNodeClick(node.id, node.prompt)}
          />
        ))}

        {/* Central Command Button — flat, no glow */}
        <div className="relative z-40">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleCommandClick}
            className={cn(
              "px-6 py-2 border flex items-center gap-3 transition-colors duration-150",
              isAnyActive 
                ? "bg-[#DC2626] border-[#DC2626] text-black" 
                : "bg-black border-[#DC2626] hover:bg-[#DC2626]/10"
            )}
          >
            <Activity className={cn("w-5 h-5", isAnyActive ? "text-black animate-pulse" : "text-[#DC2626]")} />
            <span className={cn("font-black text-sm tracking-[0.15em] uppercase", isAnyActive ? "text-black" : "text-[#DC2626]")}>
              Command
            </span>
          </motion.button>
        </div>

        {/* Corner Accents — minimal geometric marks */}
        <div className="absolute top-8 left-8 z-30 flex flex-col gap-2 opacity-30">
          <div className="w-8 h-[1px] bg-white" />
          <div className="h-8 w-[1px] bg-white" />
        </div>
        <div className="absolute top-8 right-8 z-30 flex flex-col items-end gap-2 opacity-30">
          <div className="w-8 h-[1px] bg-white" />
          <div className="h-8 w-[1px] bg-white" />
        </div>
      </div>
    </div>
  )
}

export default AgentSystemGrid;
