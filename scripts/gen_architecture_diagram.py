import graphviz

g = graphviz.Digraph("architecture", format="png")
g.attr(rankdir="TB", bgcolor="white", fontname="Helvetica", nodesep="0.4", ranksep="0.55")
g.attr("node", fontname="Helvetica", fontsize="12", shape="box", style="rounded,filled",
       color="#2b2b2b", fontcolor="#1a1a1a")

def node(name, label, fill, shape="box", width=None):
    kwargs = {"fillcolor": fill, "shape": shape}
    if width:
        kwargs["width"] = width
    g.node(name, label, **kwargs)

node("recruiter", "Recruiter\n\"Find top 5 Python devs,\n2+ yrs experience,\nshortlist them\"", "#E8F0FE", shape="ellipse")
node("agent", "AI Recruitment Agent\n(Claude - tool use)\nai_agent/agent.py", "#D9E8FB")
node("gateway", "MCP Gateway\nauth (JWT) -> authorize (RBAC)\n-> audit log -> forward\nmcp_gateway/gateway.py", "#FCE8D6")
node("mcpserver", "MCP Server\nsearch_candidates, rank_candidates_tool,\nshortlist_candidates, ...\nmcp_server/server.py", "#D9F2D9")
node("backend", "Backend Services\ncrud.py (data access)\nmatching.py (score & rank)", "#D9F2D9")
node("db", "Database\ncandidates | jobs | shortlists\nshortlist_items | audit_logs", "#EDEDED", shape="cylinder")
node("response", "Final AI Response\n(ranked shortlist,\nsaved to DB)", "#E8F0FE", shape="ellipse")

g.edge("recruiter", "agent", label=" natural language request")
g.edge("agent", "gateway", label=" MCP Client\n(HTTP + JWT)")
g.edge("gateway", "mcpserver", label=" MCP protocol\n(authorized only)")
g.edge("mcpserver", "backend", label=" match / rank / shortlist")
g.edge("backend", "db", label=" SQLAlchemy ORM")
g.edge("db", "backend", label=" candidate & job data", style="dashed")
g.edge("backend", "mcpserver", label=" scored results", style="dashed")
g.edge("mcpserver", "gateway", label=" tool result", style="dashed")
g.edge("gateway", "agent", label=" JSON result\n(+ audit logged)", style="dashed")
g.edge("agent", "response", label=" summarize")

g.render("docs/architecture-diagram", cleanup=True)
print("done")
