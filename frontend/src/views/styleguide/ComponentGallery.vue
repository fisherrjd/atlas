<script setup lang="ts">
import { SettingsIcon } from '@lucide/vue'
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

const agreed = ref(false)
const notifications = ref(true)
const flavor = ref<string>()
</script>

<template>
  <div class="space-y-8">
    <div class="space-y-3">
      <h3 class="text-sm font-medium text-muted-foreground">Buttons</h3>
      <div class="flex flex-wrap items-center gap-2">
        <Button>Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="link">Link</Button>
        <Button variant="destructive">Destructive</Button>
        <Button disabled>Disabled</Button>
        <Button variant="outline">
          <SettingsIcon />
          With icon
        </Button>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button size="lg">Large</Button>
        <Button>Default</Button>
        <Button size="sm">Small</Button>
        <Button size="xs">Extra small</Button>
        <Button size="icon" aria-label="Settings"><SettingsIcon /></Button>
      </div>
    </div>

    <div class="space-y-3">
      <h3 class="text-sm font-medium text-muted-foreground">Badges</h3>
      <div class="flex flex-wrap items-center gap-2">
        <Badge>Default</Badge>
        <Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge>
        <Badge variant="destructive">Destructive</Badge>
      </div>
    </div>

    <div class="grid gap-6 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>A card</CardTitle>
          <CardDescription>With a form row of every input primitive.</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="gallery-name">Name</Label>
            <Input id="gallery-name" placeholder="Jade" />
          </div>
          <div class="space-y-2">
            <Label for="gallery-disabled">Disabled input</Label>
            <Input id="gallery-disabled" disabled placeholder="Can't touch this" />
          </div>
          <div class="space-y-2">
            <Label>Flavor</Label>
            <Select v-model="flavor">
              <SelectTrigger class="w-full">
                <SelectValue placeholder="Pick a flavor" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="earthy">Earthy</SelectItem>
                <SelectItem value="grapebox">Grapebox</SelectItem>
                <SelectItem value="other">Something else</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-center gap-2">
            <Checkbox id="gallery-agree" v-model="agreed" />
            <Label for="gallery-agree">Agree to nothing in particular</Label>
          </div>
          <div class="flex items-center gap-2">
            <Switch id="gallery-notify" v-model="notifications" />
            <Label for="gallery-notify">Notifications</Label>
          </div>
        </CardContent>
        <CardFooter class="gap-2">
          <Button size="sm">Save</Button>
          <Button size="sm" variant="ghost">Cancel</Button>
        </CardFooter>
      </Card>

      <div class="space-y-6">
        <div class="space-y-3">
          <h3 class="text-sm font-medium text-muted-foreground">Tabs</h3>
          <Tabs default-value="one">
            <TabsList>
              <TabsTrigger value="one">One</TabsTrigger>
              <TabsTrigger value="two">Two</TabsTrigger>
              <TabsTrigger value="three">Three</TabsTrigger>
            </TabsList>
            <TabsContent value="one" class="text-sm text-muted-foreground">
              First tab content.
            </TabsContent>
            <TabsContent value="two" class="text-sm text-muted-foreground">
              Second tab content.
            </TabsContent>
            <TabsContent value="three" class="text-sm text-muted-foreground">
              Third tab content.
            </TabsContent>
          </Tabs>
        </div>

        <div class="space-y-3">
          <h3 class="text-sm font-medium text-muted-foreground">Overlays</h3>
          <div class="flex flex-wrap items-center gap-2">
            <Dialog>
              <DialogTrigger as-child>
                <Button variant="outline">Open dialog</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>A dialog</DialogTitle>
                  <DialogDescription>
                    Popover surface, overlay, and focus handling — all themed.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <DialogClose as-child>
                    <Button variant="ghost">Close</Button>
                  </DialogClose>
                  <DialogClose as-child>
                    <Button>Confirm</Button>
                  </DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="outline">Dropdown</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuLabel>Menu</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>First item</DropdownMenuItem>
                <DropdownMenuItem>Second item</DropdownMenuItem>
                <DropdownMenuItem variant="destructive">Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="outline">Hover me</Button>
                </TooltipTrigger>
                <TooltipContent>A tooltip</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        <div class="space-y-3">
          <h3 class="text-sm font-medium text-muted-foreground">Toasts</h3>
          <div class="flex flex-wrap items-center gap-2">
            <Button variant="outline" @click="toast('Plain toast')">Toast</Button>
            <Button variant="outline" @click="toast.success('It worked')">Success</Button>
            <Button variant="outline" @click="toast.error('It broke')">Error</Button>
          </div>
        </div>

        <div class="space-y-3">
          <h3 class="text-sm font-medium text-muted-foreground">Skeleton</h3>
          <div class="flex items-center gap-3">
            <Skeleton class="size-10 rounded-full" />
            <div class="space-y-2">
              <Skeleton class="h-4 w-40" />
              <Skeleton class="h-4 w-24" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
