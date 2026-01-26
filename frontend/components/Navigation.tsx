'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Users, Calendar, ListTodo, Settings } from 'lucide-react';

export function Navigation() {
  const pathname = usePathname();

  const links = [
    { href: '/people', label: 'People', icon: Users },
    { href: '/meetings', label: 'Meetings', icon: Calendar },
    { href: '/review', label: 'Review', icon: ListTodo },
    { href: '/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 safe-bottom z-50">
      <div className="flex items-center justify-around">
        {links.map(({ href, label, icon: Icon }) => {
          const isActive = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn('nav-item flex-1', isActive && 'active')}
            >
              <Icon className="w-6 h-6" />
              <span className="text-xs mt-1">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
