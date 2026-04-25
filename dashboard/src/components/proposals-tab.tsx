"use client";

import { useState, useEffect } from "react";
import { FileText, Plus, Check, X, Clock, Eye, Send, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import {
  fetchContactProposals,
  createProposal,
  updateProposal,
  deleteProposal,
  type Proposal,
} from "@/lib/api";

interface ProposalsTabProps {
  contactId: number | null;
  conversationId?: number;
}

const statusColors: Record<string, string> = {
  draft: "bg-gray-500",
  sent: "bg-blue-500",
  accepted: "bg-green-500",
  rejected: "bg-red-500",
  expired: "bg-orange-500",
};

export function ProposalsTab({ contactId, conversationId }: ProposalsTabProps) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(false);
  const [newProposalOpen, setNewProposalOpen] = useState(false);
  const [newProposal, setNewProposal] = useState({
    title: "",
    content: "",
    value_cents: "",
  });

  useEffect(() => {
    if (!contactId) {
      setProposals([]);
      return;
    }
    loadProposals();
  }, [contactId]);

  const loadProposals = async () => {
    if (!contactId) return;
    setLoading(true);
    try {
      const data = await fetchContactProposals(contactId);
      setProposals(data.proposals);
    } catch (err) {
      console.error("Failed to load proposals:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!contactId) return;
    try {
      await createProposal(contactId, {
        title: newProposal.title,
        content: newProposal.content,
        conversation_id: conversationId,
        value_cents: newProposal.value_cents ? parseInt(newProposal.value_cents) : undefined,
      });
      setNewProposal({ title: "", content: "", value_cents: "" });
      setNewProposalOpen(false);
      loadProposals();
    } catch (err) {
      console.error("Failed to create proposal:", err);
    }
  };

  const handleUpdateStatus = async (proposalId: number, status: string) => {
    try {
      await updateProposal(proposalId, { status });
      loadProposals();
    } catch (err) {
      console.error("Failed to update proposal:", err);
    }
  };

  const handleDelete = async (proposalId: number) => {
    if (!confirm("Delete this proposal?")) return;
    try {
      await deleteProposal(proposalId);
      loadProposals();
    } catch (err) {
      console.error("Failed to delete proposal:", err);
    }
  };

  const formatCurrency = (cents: number | null, currency: string) => {
    if (!cents) return "";
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: currency || "IDR",
    }).format(cents / 100);
  };

  if (!contactId) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-40 text-muted-foreground">
          Select a contact to view proposals
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <FileText className="h-4 w-4" />
          Proposals
        </CardTitle>
        <Dialog open={newProposalOpen} onOpenChange={setNewProposalOpen}>
          <DialogTrigger>
            <Button size="sm" variant="outline">
              <Plus className="h-4 w-4 mr-1" />
              New
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Proposal</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <label className="text-sm font-medium">Title</label>
                <Input
                  value={newProposal.title}
                  onChange={(e) => setNewProposal({ ...newProposal, title: e.target.value })}
                  placeholder="Proposal title"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Content</label>
                <Textarea
                  value={newProposal.content}
                  onChange={(e) => setNewProposal({ ...newProposal, content: e.target.value })}
                  rows={5}
                  placeholder="Proposal content..."
                />
              </div>
              <div>
                <label className="text-sm font-medium">Value (cents)</label>
                <Input
                  type="number"
                  value={newProposal.value_cents}
                  onChange={(e) => setNewProposal({ ...newProposal, value_cents: e.target.value })}
                  placeholder="e.g., 1000000"
                />
              </div>
              <Button onClick={handleCreate} className="w-full">Create Proposal</Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading proposals...</div>
        ) : proposals.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No proposals yet. Create your first proposal.
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((proposal) => (
              <div key={proposal.id} className="border rounded-lg p-4 space-y-2">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="font-medium">{proposal.title}</div>
                    <div className="text-sm text-muted-foreground line-clamp-2">
                      {proposal.content}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={statusColors[proposal.status] || "bg-gray-500"}>
                      {proposal.status}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(proposal.id)}
                      className="text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {proposal.value_cents && (
                  <div className="text-sm font-medium">
                    {formatCurrency(proposal.value_cents, proposal.currency)}
                  </div>
                )}

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {proposal.sent_at && (
                    <span>Sent: {new Date(proposal.sent_at).toLocaleDateString()}</span>
                  )}
                  {proposal.opened_count > 0 && (
                    <span className="flex items-center gap-1">
                      <Eye className="h-3 w-3" />
                      {proposal.opened_count}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-2">
                  {proposal.status === "draft" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleUpdateStatus(proposal.id, "sent")}
                    >
                      <Send className="h-3 w-3 mr-1" />
                      Mark Sent
                    </Button>
                  )}
                  {proposal.status === "sent" && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleUpdateStatus(proposal.id, "accepted")}
                      >
                        <Check className="h-3 w-3 mr-1" />
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleUpdateStatus(proposal.id, "rejected")}
                      >
                        <X className="h-3 w-3 mr-1" />
                        Reject
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
