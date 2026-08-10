// frontend/src/pages/Profile.tsx
// Spec page 09. Identity form backed by routers/profile.py — only the
// fields ProfileUpdate actually accepts get sent as a patch, matching
// the PATCH-semantics convention used across the rest of the API.
import { useEffect, useState } from "react";
import { Sidebar } from "../components";
import { api } from "../api";
import "./Profile.css";

interface ProfileData {
  id: string;
  email: string;
  full_name: string;
  display_name: string | null;
  bio: string | null;
  website_url: string | null;
  github_url: string | null;
  created_at: string;
}

export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    api.get<ProfileData>("/profile").then((data) => {
      setProfile(data);
      setDisplayName(data.display_name ?? "");
      setBio(data.bio ?? "");
    });
  }, []);

  async function handleSave() {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const updated = await api.patch<ProfileData>("/profile", { display_name: displayName, bio });
      setProfile(updated);
      setSaveMessage("Saved.");
    } catch {
      setSaveMessage("Couldn't save your changes.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!profile) {
    return (
      <div className="app-shell">
        <Sidebar />
        <main className="app-main">
          <p className="page-header__meta">Loading profile…</p>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <h1>Profile</h1>
        </div>

        <div className="profile__header card">
          <div className="profile__avatar">{profile.full_name.charAt(0).toUpperCase()}</div>
          <div>
            <h2>{profile.full_name}</h2>
            <p className="page-header__meta">{profile.email}</p>
            <p className="page-header__meta">Member since {new Date(profile.created_at).toLocaleDateString()}</p>
          </div>
        </div>

        <div className="card profile__form">
          <label>
            <span>Display name</span>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>
            <span>Bio</span>
            <textarea rows={4} value={bio} onChange={(e) => setBio(e.target.value)} />
          </label>
          <button className="btn btn--fill" onClick={handleSave} disabled={isSaving}>
            {isSaving ? "Saving…" : "Save changes"}
          </button>
          {saveMessage && <p className="page-header__meta">{saveMessage}</p>}
        </div>
      </main>
    </div>
  );
}
