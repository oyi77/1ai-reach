"use client";

import { useState, useEffect } from "react";
import { Tag, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  fetchWahaLabels,
  fetchConversationLabels,
  assignLabelToConversation,
  removeLabelFromConversation,
  type WahaLabel,
} from "@/lib/api";

interface LabelsFilterProps {
  waNumberId: string;
  conversationId: number | null;
  onFilterChange?: (labelIds: number[]) => void;
}

export function LabelsFilter({ waNumberId, conversationId, onFilterChange }: LabelsFilterProps) {
  const [availableLabels, setAvailableLabels] = useState<WahaLabel[]>([]);
  const [assignedLabels, setAssignedLabels] = useState<WahaLabel[]>([]);
  const [selectedFilter, setSelectedFilter] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadLabels();
  }, [waNumberId, conversationId]);

  const loadLabels = async () => {
    setLoading(true);
    try {
      const [available, assigned] = await Promise.all([
        fetchWahaLabels(waNumberId),
        conversationId ? fetchConversationLabels(conversationId) : Promise.resolve({ labels: [] }),
      ]);
      setAvailableLabels(available.labels);
      setAssignedLabels(assigned.labels);
    } catch (err) {
      console.error("Failed to load labels:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleAssignLabel = async (labelId: number) => {
    if (!conversationId) return;
    try {
      await assignLabelToConversation(conversationId, labelId);
      loadLabels();
    } catch (err) {
      console.error("Failed to assign label:", err);
    }
  };

  const handleRemoveLabel = async (labelId: number) => {
    if (!conversationId) return;
    try {
      await removeLabelFromConversation(conversationId, labelId);
      loadLabels();
    } catch (err) {
      console.error("Failed to remove label:", err);
    }
  };

  const toggleFilter = (labelId: number) => {
    const newFilter = selectedFilter.includes(labelId)
      ? selectedFilter.filter((id) => id !== labelId)
      : [...selectedFilter, labelId];
    setSelectedFilter(newFilter);
    onFilterChange?.(newFilter);
  };

  const unassignedLabels = availableLabels.filter(
    (label) => !assignedLabels.some((al) => al.id === label.id)
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium flex items-center gap-2">
          <Tag className="h-4 w-4" />
          Labels
        </div>
        {selectedFilter.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSelectedFilter([]);
              onFilterChange?.([]);
            }}
          >
            Clear filter
          </Button>
        )}
      </div>

      <div className="flex flex-wrap gap-1">
        {assignedLabels.map((label) => (
          <Badge
            key={label.id}
            style={{ backgroundColor: label.color || undefined }}
            className="cursor-pointer"
            onClick={() => toggleFilter(label.id)}
            variant={selectedFilter.includes(label.id) ? "default" : "secondary"}
          >
            {label.name}
            {conversationId && (
              <X
                className="h-3 w-3 ml-1"
                onClick={(e) => {
                  e.stopPropagation();
                  handleRemoveLabel(label.id);
                }}
              />
            )}
          </Badge>
        ))}

        {conversationId && unassignedLabels.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger>
              <Button variant="outline" size="sm" className="h-6 px-2">
                + Add
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {unassignedLabels.map((label) => (
                <DropdownMenuItem
                  key={label.id}
                  onClick={() => handleAssignLabel(label.id)}
                >
                  <span
                    className="w-3 h-3 rounded-full mr-2"
                    style={{ backgroundColor: label.color || undefined }}
                  />
                  {label.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  );
}
