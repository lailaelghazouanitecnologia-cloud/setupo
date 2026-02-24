'use client';

import React from 'react';
import { Menu } from 'lucide-react';
import { useLayout } from '@/hooks/useLayout';
import { cn } from '@/lib/utils';

interface SidebarToggleProps 
{
  className?: string;
}

export function SidebarToggle({ className }: SidebarToggleProps) 
{
  const { sidebar } = useLayout();

  return (
    <button
      type="button"
      onClick={sidebar.toggle}
      className={cn(
        'flex items-center justify-center p-2 rounded-lg hover:bg-muted/50 transition-colors focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
      aria-label="Toggle sidebar"
    >
      <Menu className="w-4 h-4" />
    </button>
  );
}