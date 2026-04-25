"use client";

import { useState, useEffect } from "react";
import { User, Building2, Link, MapPin, Calendar, Edit2, Save, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { fetchContactProfile, updateContactProfile, type Contact, type ContactProfile } from "@/lib/api";

interface ContactProfilePanelProps {
  contactId: number | null;
  contact?: Contact | null;
}

export function ContactProfilePanel({ contactId, contact }: ContactProfilePanelProps) {
  const [profile, setProfile] = useState<ContactProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [formData, setFormData] = useState<Partial<ContactProfile>>({});

  useEffect(() => {
    if (!contactId) {
      setProfile(null);
      return;
    }

    setLoading(true);
    fetchContactProfile(contactId)
      .then((data) => {
        setProfile(data.profile);
        setFormData(data.profile || {});
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [contactId]);

  const handleSave = async () => {
    if (!contactId) return;
    try {
      const updated = await updateContactProfile(contactId, formData);
      setProfile(updated.profile);
      setEditing(false);
    } catch (err) {
      console.error("Failed to update profile:", err);
    }
  };

  if (!contactId || loading) {
    return (
      <Card className="h-full">
        <CardContent className="flex items-center justify-center h-40 text-muted-foreground">
          {loading ? "Loading profile..." : "Select a contact to view profile"}
        </CardContent>
      </Card>
    );
  }

  const displayContact = contact;

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <User className="h-4 w-4" />
          Contact Profile
        </CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => (editing ? handleSave() : setEditing(true))}
        >
          {editing ? <Save className="h-4 w-4" /> : <Edit2 className="h-4 w-4" />}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {displayContact && (
          <div className="space-y-1">
            <div className="font-medium text-lg">{displayContact.name}</div>
            <div className="text-sm text-muted-foreground">{displayContact.phone}</div>
          </div>
        )}

        {editing ? (
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">Status Message</label>
              <Input
                value={formData.status || ""}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                placeholder="Custom status"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Business Name</label>
              <Input
                value={formData.business_name || ""}
                onChange={(e) => setFormData({ ...formData, business_name: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Business Description</label>
              <Textarea
                value={formData.business_description || ""}
                onChange={(e) => setFormData({ ...formData, business_description: e.target.value })}
                rows={2}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Website</label>
              <Input
                value={formData.website || ""}
                onChange={(e) => setFormData({ ...formData, website: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Address</label>
              <Textarea
                value={formData.address || ""}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                rows={2}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Birthday</label>
              <Input
                type="date"
                value={formData.birthday || ""}
                onChange={(e) => setFormData({ ...formData, birthday: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.is_business || false}
                onChange={(e) => setFormData({ ...formData, is_business: e.target.checked })}
                id="is_business"
              />
              <label htmlFor="is_business" className="text-sm">Is Business Account</label>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {profile?.status && (
              <div className="flex items-center gap-2 text-sm">
                <User className="h-4 w-4 text-muted-foreground" />
                <span>{profile.status}</span>
              </div>
            )}
            {profile?.is_business && (
              <Badge variant="secondary" className="flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                Business Account
              </Badge>
            )}
            {profile?.business_name && (
              <div className="flex items-center gap-2 text-sm">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span>{profile.business_name}</span>
              </div>
            )}
            {profile?.business_description && (
              <div className="text-sm text-muted-foreground">
                {profile.business_description}
              </div>
            )}
            {profile?.website && (
              <div className="flex items-center gap-2 text-sm">
                <Link className="h-4 w-4 text-muted-foreground" />
                <a
                  href={profile.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:underline"
                >
                  {profile.website}
                </a>
              </div>
            )}
            {profile?.address && (
              <div className="flex items-start gap-2 text-sm">
                <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                <span>{profile.address}</span>
              </div>
            )}
            {profile?.birthday && (
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span>{profile.birthday}</span>
              </div>
            )}
            {!profile && (
              <div className="text-sm text-muted-foreground">
                No profile information. Click edit to add details.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
