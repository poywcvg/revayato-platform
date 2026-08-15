<script setup lang="ts">
import type { Component } from 'vue'
import type { CinematicIconName } from '~/types'
import AlertTriangle from '~icons/lucide/triangle-alert'
import ArrowLeft from '~icons/lucide/arrow-left'
import ArrowRight from '~icons/lucide/arrow-right'
import ArrowUp from '~icons/lucide/arrow-up'
import ArrowUpRight from '~icons/lucide/arrow-up-right'
import Audio from '~icons/lucide/audio-lines'
import Badge from '~icons/lucide/badge'
import Bookmark from '~icons/lucide/bookmark'
import BookmarkCheck from '~icons/lucide/bookmark-check'
import Bell from '~icons/lucide/bell'
import BellRing from '~icons/lucide/bell-ring'
import Bolt from '~icons/lucide/zap'
import Brain from '~icons/lucide/brain'
import BrainCircuit from '~icons/lucide/brain-circuit'
import Calendar from '~icons/lucide/calendar-days'
import Captions from '~icons/lucide/captions'
import Check from '~icons/lucide/check'
import CheckCircle from '~icons/lucide/circle-check'
import ChevronDown from '~icons/lucide/chevron-down'
import ChevronLeft from '~icons/lucide/chevron-left'
import ChevronRight from '~icons/lucide/chevron-right'
import ChevronUp from '~icons/lucide/chevron-up'
import Clapperboard from '~icons/lucide/clapperboard'
import Clock from '~icons/lucide/clock-3'
import Comment from '~icons/lucide/message-circle-more'
import Comments from '~icons/lucide/messages-square'
import Document from '~icons/lucide/file-text'
import Download from '~icons/lucide/download'
import Edit from '~icons/lucide/pencil-line'
import Eye from '~icons/lucide/eye'
import EyeOff from '~icons/lucide/eye-off'
import FastForward from '~icons/lucide/fast-forward'
import Feather from '~icons/lucide/feather'
import Film from '~icons/lucide/film'
import Gauge from '~icons/lucide/gauge'
import Maximize from '~icons/lucide/maximize'
import Minimize from '~icons/lucide/minimize'
import Pause from '~icons/lucide/pause'
import PictureInPicture from '~icons/lucide/picture-in-picture-2'
import Rewind from '~icons/lucide/rewind'
import Ghost from '~icons/lucide/ghost'
import Globe from '~icons/lucide/globe'
import Grid from '~icons/lucide/grid-2x2'
import Heart from '~icons/lucide/heart'
import History from '~icons/lucide/history'
import Home from '~icons/lucide/house'
import ImageOff from '~icons/lucide/image-off'
import Info from '~icons/lucide/info'
import Language from '~icons/lucide/languages'
import Layers from '~icons/lucide/layers-3'
import Leaf from '~icons/lucide/leaf'
import ListVideo from '~icons/lucide/list-video'
import Lock from '~icons/lucide/lock-keyhole'
import Login from '~icons/lucide/log-in'
import Logout from '~icons/lucide/log-out'
import Map from '~icons/lucide/map'
import Masks from '~icons/lucide/drama'
import Menu from '~icons/lucide/menu'
import Moon from '~icons/lucide/moon'
import Sun from '~icons/lucide/sun'
import Palette from '~icons/lucide/palette'
import Play from '~icons/lucide/play'
import Puzzle from '~icons/lucide/puzzle'
import Refresh from '~icons/lucide/rotate-cw'
import Rocket from '~icons/lucide/rocket'
import Search from '~icons/lucide/search'
import Investigate from '~icons/lucide/scan-search'
import Settings from '~icons/lucide/settings-2'
import Share from '~icons/lucide/share-2'
import ShieldAlert from '~icons/lucide/shield-alert'
import ShieldCheck from '~icons/lucide/shield-check'
import SignalOff from '~icons/lucide/signal-zero'
import Sliders from '~icons/lucide/sliders-horizontal'
import Smile from '~icons/lucide/smile'
import Sparkles from '~icons/lucide/sparkles'
import Star from '~icons/lucide/star'
import Tag from '~icons/lucide/tag'
import TrendingUp from '~icons/lucide/trending-up'
import Trash from '~icons/lucide/trash-2'
import User from '~icons/lucide/user-round'
import UserPlus from '~icons/lucide/user-round-plus'
import Users from '~icons/lucide/users-round'
import Volume1 from '~icons/lucide/volume-1'
import Volume2 from '~icons/lucide/volume-2'
import VolumeX from '~icons/lucide/volume-x'
import Wand from '~icons/lucide/wand-sparkles'
import X from '~icons/lucide/x'

const props = withDefaults(defineProps<{
  name: CinematicIconName
  label?: string
  filled?: boolean
  strokeWidth?: number
}>(), {
  label: '',
  filled: false,
  strokeWidth: 1.8,
})

const iconComponents: Record<CinematicIconName, Component> = {
  'ai': BrainCircuit,
  'alert-triangle': AlertTriangle,
  'animation': Palette,
  'arrow-left': ArrowLeft,
  'arrow-right': ArrowRight,
  'arrow-up': ArrowUp,
  'arrow-up-right': ArrowUpRight,
  'audio': Audio,
  'badge': Badge,
  'bookmark': Bookmark,
  'bookmark-check': BookmarkCheck,
  'bell': Bell,
  'bell-ring': BellRing,
  'bolt': Bolt,
  'calendar': Calendar,
  'calm': Leaf,
  'captions': Captions,
  'check': Check,
  'check-circle': CheckCircle,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'chevron-up': ChevronUp,
  'clapperboard': Clapperboard,
  'clock': Clock,
  'comment': Comment,
  'comments': Comments,
  'document': Document,
  'download': Download,
  'edit': Edit,
  'exciting': Bolt,
  'eye': Eye,
  'eye-off': EyeOff,
  'family': Users,
  'fast-forward': FastForward,
  'film': Film,
  'gauge': Gauge,
  'globe': Globe,
  'grid': Grid,
  'heart': Heart,
  'history': History,
  'home': Home,
  'image-off': ImageOff,
  'info': Info,
  'investigate': Investigate,
  'language': Language,
  'layers': Layers,
  'light': Feather,
  'list-video': ListVideo,
  'lock': Lock,
  'login': Login,
  'logout': Logout,
  'map': Map,
  'masks': Masks,
  'maximize': Maximize,
  'menu': Menu,
  'minimize': Minimize,
  'mood': Moon,
  'moon': Moon,
  'movie': Film,
  'palette': Palette,
  'pause': Pause,
  'picture-in-picture': PictureInPicture,
  'play': Play,
  'profile': User,
  'rewind': Rewind,
  'puzzle': Puzzle,
  'quality': Badge,
  'refresh': Refresh,
  'resume': History,
  'rocket': Rocket,
  'scary': Ghost,
  'search': Search,
  'series': ListVideo,
  'settings': Settings,
  'share': Share,
  'shield-alert': ShieldAlert,
  'shield-check': ShieldCheck,
  'signal-off': SignalOff,
  'sliders': Sliders,
  'smile': Smile,
  'sparkles': Sparkles,
  'star': Star,
  'subtitle': Captions,
  'sun': Sun,
  'tag': Tag,
  'thoughtful': Brain,
  'trailer': Clapperboard,
  'trash': Trash,
  'trend': TrendingUp,
  'user': User,
  'user-plus': UserPlus,
  'users': Users,
  'volume': Volume2,
  'volume-1': Volume1,
  'volume-x': VolumeX,
  'wand': Wand,
  'x': X,
}

const iconComponent = computed(() => iconComponents[props.name])
</script>

<template>
  <component
    :is="iconComponent"
    class="cinematic-icon"
    :class="filled && 'cinematic-icon--filled'"
    :stroke-width="strokeWidth"
    :role="label ? 'img' : undefined"
    :aria-label="label || undefined"
    :aria-hidden="label ? undefined : 'true'"
    focusable="false"
  />
</template>
