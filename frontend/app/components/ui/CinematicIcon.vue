<script setup lang="ts">
import type { Component } from 'vue'
import type { CinematicIconName } from '~/types'
import AlertTriangle from '~icons/lucide/triangle-alert'
import ArrowLeft from '~icons/lucide/arrow-left'
import ArrowRight from '~icons/lucide/arrow-right'
import ArrowUp from '~icons/lucide/arrow-up'
import Smartphone from '~icons/lucide/smartphone'
import ArrowUpRight from '~icons/lucide/arrow-up-right'
import Audio from '~icons/lucide/mic-vocal'
import Badge from '~icons/lucide/badge'
import Bookmark from '~icons/lucide/bookmark'
import BookmarkCheck from '~icons/lucide/bookmark-check'
import Bell from '~icons/lucide/bell'
import Bolt from '~icons/lucide/zap'
import Brain from '~icons/lucide/brain'
import BrainCircuit from '~icons/lucide/brain-circuit'
import Calendar from '~icons/lucide/calendar-days'
import Captions from '~icons/lucide/captions'
import CaptionsOff from '~icons/lucide/captions-off'
import Check from '~icons/lucide/check'
import CheckCircle from '~icons/lucide/circle-check'
import AlertCircle from '~icons/lucide/circle-alert'
import XCircle from '~icons/lucide/circle-x'
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
import FileWarning from '~icons/lucide/file-warning'
import Film from '~icons/lucide/film'
import Flag from '~icons/lucide/flag'
import Gauge from '~icons/lucide/gauge'
import Maximize from '~icons/lucide/maximize'
import Minimize from '~icons/lucide/minimize'
import Minus from '~icons/lucide/minus'
import Plus from '~icons/lucide/plus'
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
import Loader from '~icons/lucide/loader-circle'
import Language from '~icons/lucide/languages'
import Layers from '~icons/lucide/layers-3'
import Leaf from '~icons/lucide/leaf'
import ListVideo from '~icons/lucide/list-video'
import Tv from '~icons/lucide/tv-minimal-play'
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
import Send from '~icons/lucide/send'
import Investigate from '~icons/lucide/scan-search'
import Settings from '~icons/lucide/settings-2'
import Share from '~icons/lucide/share-2'
import ShieldAlert from '~icons/lucide/shield-alert'
import ShieldCheck from '~icons/lucide/shield-check'
import SignalOff from '~icons/lucide/signal-zero'
import Sliders from '~icons/lucide/sliders-horizontal'
import Smile from '~icons/lucide/smile'
import SmilePlus from '~icons/lucide/smile-plus'
import Sparkles from '~icons/lucide/sparkles'
import Star from '~icons/lucide/star'
import Tag from '~icons/lucide/tag'
import TrendingUp from '~icons/lucide/trending-up'
import Trophy from '~icons/lucide/trophy'
import Trash from '~icons/lucide/trash-2'
import User from '~icons/lucide/user-round'
import UserPlus from '~icons/lucide/user-round-plus'
import Users from '~icons/lucide/users-round'
import Volume1 from '~icons/lucide/volume-1'
import Volume2 from '~icons/lucide/volume-2'
import VolumeOff from '~icons/lucide/volume-off'
import VolumeX from '~icons/lucide/volume-x'
import Wand from '~icons/lucide/wand-sparkles'
import X from '~icons/lucide/x'
import GBaby from '~icons/lucide/baby'
import GBomb from '~icons/lucide/bomb'
import GBookUser from '~icons/lucide/book-user'
import GBrain from '~icons/lucide/brain'
import GCastle from '~icons/lucide/castle'
import GDrama from '~icons/lucide/drama'
import GFingerprintPattern from '~icons/lucide/fingerprint-pattern'
import GFlower2 from '~icons/lucide/flower-2'
import GGavel from '~icons/lucide/gavel'
import GHouseHeart from '~icons/lucide/house-heart'
import GKeyRound from '~icons/lucide/key-round'
import GLandmark from '~icons/lucide/landmark'
import GLaugh from '~icons/lucide/laugh'
import GMountainSnow from '~icons/lucide/mountain-snow'
import GMusic from '~icons/lucide/music'
import GMusic2 from '~icons/lucide/music-2'
import GOrbit from '~icons/lucide/orbit'
import GRabbit from '~icons/lucide/rabbit'
import GRose from '~icons/lucide/rose'
import GScanEye from '~icons/lucide/scan-eye'
import GSkull from '~icons/lucide/skull'
import GSunset from '~icons/lucide/sunset'
import GSwords from '~icons/lucide/swords'
import GTornado from '~icons/lucide/tornado'
import GTv from '~icons/lucide/tv'
import GTvMinimal from '~icons/lucide/tv-minimal'
import GVenetianMask from '~icons/lucide/venetian-mask'
import GVideo from '~icons/lucide/video'
import GVolleyball from '~icons/lucide/volleyball'
import GVote from '~icons/lucide/vote'
import GZap from '~icons/lucide/zap'
import Crown from '~icons/lucide/crown'
import CalendarClock from '~icons/lucide/calendar-clock'
import Earth from '~icons/lucide/earth'
import LayoutGrid from '~icons/lucide/layout-grid'
import CircleUserRound from '~icons/lucide/circle-user-round'
import Flame from '~icons/lucide/flame'
import Gem from '~icons/lucide/gem'
import Popcorn from '~icons/lucide/popcorn'
import LayoutDashboard from '~icons/lucide/layout-dashboard'
import Compass from '~icons/lucide/compass'
import Rabbit from '~icons/lucide/rabbit'
import StepForward from '~icons/lucide/step-forward'
import MessageSquareText from '~icons/lucide/message-square-text'
import BellDot from '~icons/lucide/bell-dot'

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
  'alert-circle': AlertCircle,
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
  'bell-ring': BellDot,
  'bolt': Bolt,
  'calendar': Calendar,
  'calm': Leaf,
  'captions': Captions,
  'captions-off': CaptionsOff,
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
  'smartphone': Smartphone,
  'edit': Edit,
  'exciting': Bolt,
  'eye': Eye,
  'eye-off': EyeOff,
  'family': Users,
  'fast-forward': FastForward,
  'file-warning': FileWarning,
  'film': Film,
  'flag': Flag,
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
  'loader': Loader,
  'lock': Lock,
  'login': Login,
  'logout': Logout,
  'map': Map,
  'masks': Masks,
  'maximize': Maximize,
  'menu': Menu,
  'minimize': Minimize,
  'minus': Minus,
  'mood': SmilePlus,
  'moon': Moon,
  'movie': Clapperboard,
  'palette': Palette,
  'pause': Pause,
  'picture-in-picture': PictureInPicture,
  'play': Play,
  'plus': Plus,
  'profile': User,
  'rewind': Rewind,
  'puzzle': Puzzle,
  'quality': Badge,
  'refresh': Refresh,
  'resume': History,
  'rocket': Rocket,
  'scary': Ghost,
  'search': Search,
  'send': Send,
  'series': Tv,
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
  'trophy': Trophy,
  'trend': TrendingUp,
  'user': User,
  'user-plus': UserPlus,
  'users': Users,
  'volume': Volume2,
  'volume-1': Volume1,
  'volume-off': VolumeOff,
  'volume-x': VolumeX,
  'wand': Wand,
  'x': X,
  'genre-drama': GDrama,
  'genre-sci-fi': GOrbit,
  'genre-crime': GFingerprintPattern,
  'genre-adventure': GMountainSnow,
  'genre-mystery': GKeyRound,
  'genre-romance': GRose,
  'genre-action': GBomb,
  'genre-fantasy': GCastle,
  'genre-comedy': GLaugh,
  'genre-horror': GSkull,
  'genre-family': GHouseHeart,
  'genre-animation': GRabbit,
  'genre-thriller': GScanEye,
  'genre-documentary': GVideo,
  'genre-biography': GBookUser,
  'genre-history': GLandmark,
  'genre-war': GSwords,
  'genre-western': GSunset,
  'genre-music': GMusic,
  'genre-musical': GMusic2,
  'genre-sport': GVolleyball,
  'genre-superhero': GZap,
  'genre-anime': GFlower2,
  'genre-psychological': GBrain,
  'genre-political': GVote,
  'genre-disaster': GTornado,
  'genre-legal': GGavel,
  'genre-kids': GBaby,
  'genre-reality-tv': GTv,
  'genre-film-noir': GVenetianMask,
  'genre-tv-movie': GTvMinimal,
  'account': CircleUserRound,
  'cartoon': Rabbit,
  'categories': LayoutGrid,
  'continue': StepForward,
  'countries': Earth,
  'dashboard': LayoutDashboard,
  'discover': Compass,
  'featured': Gem,
  'hot': Flame,
  'party': Popcorn,
  'schedule': CalendarClock,
  'support': MessageSquareText,
  'top250': Crown,
  'x-circle': XCircle,
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
