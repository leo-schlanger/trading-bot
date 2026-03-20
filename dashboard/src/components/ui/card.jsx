import { cn } from "@/lib/utils"

export function Card({ className, variant = "default", ...props }) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card text-card-foreground shadow-sm transition-all duration-200",
        variant === "glass" && "bg-card/80 backdrop-blur-xl border-border/50",
        variant === "gradient" && "bg-gradient-to-br from-card to-card/80 border-border/50",
        className
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }) {
  return (
    <div
      className={cn("flex flex-col space-y-1.5 p-6", className)}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }) {
  return (
    <h3
      className={cn("font-semibold leading-none tracking-tight text-foreground", className)}
      {...props}
    />
  )
}

export function CardDescription({ className, ...props }) {
  return (
    <p
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export function CardContent({ className, ...props }) {
  return <div className={cn("p-6 pt-0", className)} {...props} />
}

export function CardFooter({ className, ...props }) {
  return (
    <div
      className={cn("flex items-center p-6 pt-0", className)}
      {...props}
    />
  )
}
