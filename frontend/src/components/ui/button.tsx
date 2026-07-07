import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva } from 'class-variance-authority';
import type { VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/85',
        outline:
          'border border-border bg-transparent text-foreground hover:border-primary hover:text-primary',
        ghost: 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
        destructive:
          'border border-destructive/40 bg-destructive/15 text-destructive hover:bg-destructive/25',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        icon: 'size-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : 'button';
  return (
    <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />
  );
}

export { Button };
