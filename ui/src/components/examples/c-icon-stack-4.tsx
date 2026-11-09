import { IconStack } from "@/components/reui/icon-stack"
import { CheckIcon } from "lucide-react"

export function Pattern() {
  return (
    <div className="flex items-center justify-center">
      <IconStack aria-hidden="true" className="text-primary h-24 w-22">
        <span className="bg-background text-primary flex size-8 items-center justify-center rounded-full border shadow-xs">
          <CheckIcon className="size-4" />
        </span>
      </IconStack>
    </div>
  )
}