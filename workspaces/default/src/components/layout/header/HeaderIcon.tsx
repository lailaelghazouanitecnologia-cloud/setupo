'use client';

import React from 'react';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderIconProps 
{
  icon: LucideIcon;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
  badge?: number;
}

export function HeaderIcon({ 
  icon: Icon, 
  onClick, 
  className, 
  disabled = false,
  badge 
}: HeaderIconProps) 
{
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'header-icon focus-ring',
        {
          'opacity-50 cursor-not-allowed': disabled,
          'relative': badge !== undefined
        },
        className
      )}
      aria-label="Header action"
    >
      <Icon className="w-4 h-4" />
      {badge !== undefined && badge > 0 && (
        <span className="users-badge">
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  );
}
