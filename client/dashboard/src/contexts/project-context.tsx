"use client";

import React, { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import {
  listProjects, listWorkspaces,
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
} from "@/lib/api/client";
import { useAuth } from "./auth-context";

// ── Types ──────────────────────────────────────────────────

export interface ProjectInfo {
  id: string;
  name: string;
  api_key_hash?: string;
  owner?: string;
  created_at?: string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  path: string;
  description: string;
  instance_id?: string | null;
  ws_type?: string;
  stack?: string;
  exists?: boolean;
}

interface ProjectState {
  projects: ProjectInfo[];
  activeProject: ProjectInfo | null;
  workspaces: WorkspaceInfo[];
  activeWorkspace: WorkspaceInfo | null;
  loading: boolean;
  error: string | null;
}

interface ProjectActions {
  setActiveProject: (project: ProjectInfo | null) => void;
  setActiveWorkspace: (workspace: WorkspaceInfo | null) => void;
  refreshProjects: () => Promise<void>;
  refreshWorkspaces: (projectId?: string) => Promise<void>;
  createProject: (name: string) => Promise<ProjectInfo>;
  deleteProject: (id: string) => Promise<void>;
}

type ProjectContextValue = ProjectState & ProjectActions;

// ── Context ────────────────────────────────────────────────

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within <ProjectProvider>");
  return ctx;
}

// ── Provider ───────────────────────────────────────────────

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();

  const [state, setState] = useState<ProjectState>({
    projects: [],
    activeProject: null,
    workspaces: [],
    activeWorkspace: null,
    loading: true,
    error: null,
  });

  // Load projects when authenticated
  useEffect(() => {
    if (!token) {
      setState({ projects: [], activeProject: null, workspaces: [], activeWorkspace: null, loading: false, error: null });
      return;
    }
    loadProjects();
  }, [token]);

  async function loadProjects() {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await listProjects();
      const projects: ProjectInfo[] = res.projects || [];
      setState((s) => {
        // Restore active project from localStorage
        const savedId = localStorage.getItem("nso_active_project");
        const restored = savedId ? projects.find((p) => p.id === savedId) || null : null;
        return { ...s, projects, activeProject: restored || projects[0] || null, loading: false };
      });
    } catch (err: any) {
      setState((s) => ({ ...s, loading: false, error: err.message || "Failed to load projects" }));
    }
  }

  // Load workspaces when active project changes
  useEffect(() => {
    const pid = state.activeProject?.id;
    if (!pid) {
      setState((s) => ({ ...s, workspaces: [], activeWorkspace: null }));
      return;
    }
    loadWorkspaces(pid);
  }, [state.activeProject?.id]);

  async function loadWorkspaces(projectId: string) {
    try {
      const res = await listWorkspaces(projectId);
      const workspaces: WorkspaceInfo[] = res.workspaces || [];
      setState((s) => {
        const savedId = localStorage.getItem("nso_active_workspace");
        const restored = savedId ? workspaces.find((w) => w.id === savedId) || null : null;
        return { ...s, workspaces, activeWorkspace: restored || workspaces[0] || null };
      });
    } catch {
      setState((s) => ({ ...s, workspaces: [], activeWorkspace: null }));
    }
  }

  const setActiveProject = useCallback((project: ProjectInfo | null) => {
    if (project) localStorage.setItem("nso_active_project", project.id);
    else localStorage.removeItem("nso_active_project");
    setState((s) => ({ ...s, activeProject: project, workspaces: [], activeWorkspace: null }));
  }, []);

  const setActiveWorkspace = useCallback((workspace: WorkspaceInfo | null) => {
    if (workspace) localStorage.setItem("nso_active_workspace", workspace.id);
    else localStorage.removeItem("nso_active_workspace");
    setState((s) => ({ ...s, activeWorkspace: workspace }));
  }, []);

  const refreshProjects = useCallback(async () => {
    await loadProjects();
  }, [token]);

  const refreshWorkspaces = useCallback(async (projectId?: string) => {
    const pid = projectId || state.activeProject?.id;
    if (pid) await loadWorkspaces(pid);
  }, [state.activeProject?.id]);

  const createProject = useCallback(async (name: string): Promise<ProjectInfo> => {
    const res = await apiCreateProject(name);
    const newProject: ProjectInfo = res.project;
    setState((s) => ({ ...s, projects: [...s.projects, newProject] }));
    setActiveProject(newProject);
    return newProject;
  }, [setActiveProject]);

  const deleteProject = useCallback(async (id: string) => {
    await apiDeleteProject(id);
    setState((s) => {
      const projects = s.projects.filter((p) => p.id !== id);
      const activeProject = s.activeProject?.id === id ? (projects[0] || null) : s.activeProject;
      return { ...s, projects, activeProject };
    });
  }, []);

  const value: ProjectContextValue = {
    ...state,
    setActiveProject,
    setActiveWorkspace,
    refreshProjects,
    refreshWorkspaces,
    createProject,
    deleteProject,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}
