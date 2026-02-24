'use client';

import React from 'react';
import { 
  Plus, 
  FileText, 
  Image, 
  Folder, 
  Link, 
  Power, 
  Menu 
} from 'lucide-react';
import { useLayout } from '@/hooks/useLayout';
import { HeaderIcon } from './HeaderIcon';
import { UserMenu } from './UserMenu';
import { UsersIndicator } from './UsersIndicator';
import { CreditsDisplay } from '@/components/ui/CreditsDisplay';
import { cn } from '@/lib/utils';

interface HeaderProps 
{
  className?: string;
}

export function Header({ className }: HeaderProps) 
{
  const { header, sidebar, device } = useLayout();

  return (
    <header 
      className={cn(
        'header-base',
        {
          'header-hidden': !header.visible,
          'header-shifted': sidebar.visible && !device.mobile
        },
        className
      )}
    >
      <div className="header-content">
        <HeaderLeft />
        <div className="flex-1" />
        <HeaderRight />
      </div>

      {header.loading && (
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary/20 via-primary to-primary/20 animate-pulse" />
      )}
    </header>
  );
}

function HeaderLeft() 
{
  const { sidebar } = useLayout();

  return (
    <div className="header-left">
      <button
        type="button"
        onClick={sidebar.toggle}
        className="sidebar-toggle-btn focus-ring"
        aria-label="Toggle sidebar"
      >
        <Menu className="w-4 h-4" />
      </button>
      <span className="header-company-name">Sonzar</span>
    </div>
  );
}

function HeaderRight() 
{
  const { header } = useLayout();

  const handleIconClick = (iconType: string) => {
    console.log(`${iconType} clicked`);
  };

  return (
    <div className="header-right">
      <HeaderIcon 
        icon={Plus}
        onClick={() => handleIconClick('plus')}
        disabled={header.loading}
      />
      <HeaderIcon 
        icon={FileText}
        onClick={() => handleIconClick('files')}
        disabled={header.loading}
      />
      <HeaderIcon 
        icon={Image}
        onClick={() => handleIconClick('images')}
        disabled={header.loading}
      />

      <div className="w-2" />

      <HeaderIcon 
        icon={Link}
        onClick={() => handleIconClick('link')}
        disabled={header.loading}
      />
      <HeaderIcon 
        icon={Folder}
        onClick={() => handleIconClick('folder')}
        disabled={header.loading}
      />

      <UsersIndicator 
        count={3}
        onClick={() => handleIconClick('users')}
        disabled={header.loading}
      />

      <div className="header-separator" />

      {/* Sistema de Créditos */}
      <CreditsDisplay compact />

      <div className="header-separator" />

      <HeaderIcon 
        icon={Power}
        onClick={() => handleIconClick('power')}
        disabled={header.loading}
      />

      <UserMenu />
    </div>
  );
}