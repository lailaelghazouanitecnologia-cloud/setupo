'use client';

import React from 'react';
import { 
  MessageSquare, 
  FolderOpen,
  Puzzle,
  FileText
} from 'lucide-react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { cn } from '@/lib/utils';

interface NavigationItem 
{
  icon: React.ElementType;
  label: string;
  href: string;
  badge?: number;
}

const navigationItems: NavigationItem[] = [
  { icon: MessageSquare, label: 'Chat', href: '/chat' },
  { icon: FolderOpen, label: 'Proyectos', href: '/projects' },
  { icon: Puzzle, label: 'Plugins', href: '/plugins' },
  { icon: FileText, label: 'Files', href: '/files' },
];

export function Navigation() 
{
  const pathname = usePathname();

  return (
    <nav className="space-y-1">
      {navigationItems.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href;
        
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              'flex items-center gap-3 px-2 py-1.5 rounded-md transition-colors text-sm',
              {
                'bg-sidebar-accent text-sidebar-accent-foreground font-medium': isActive,
                'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground': !isActive
              }
            )}
          >
            <Icon className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
            <span className="flex-1 truncate text-xs">{item.label}</span>
            {item.badge && (
              <span className="bg-primary text-primary-foreground text-xs rounded-full px-1.5 py-0.5 min-w-[1rem] h-4 flex items-center justify-center">
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}