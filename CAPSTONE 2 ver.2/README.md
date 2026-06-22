# MSHFI Multi-Role Dashboard

A fully responsive, frontend-only medical appointment and scheduling system dashboard UI with support for four distinct user roles: Patient, Doctor, Secretary, and Administrator.

## Features

✨ **Multi-Role Support**
- Patient Dashboard
- Doctor Dashboard
- Secretary Dashboard
- Admin Dashboard

🎨 **Design & UX**
- Responsive grid layout (1 col mobile, 2 col tablet, 4 col desktop)
- Persistent left sidebar with role badge
- Brand-colored header with user profile
- Smooth fade-up animations on card load
- Hover states with subtle transitions
- Fully keyboard accessible (Radix UI)
- Mobile-friendly drawer navigation

📊 **Dashboard Components**
- **Trend Chart**: AreaChart with gradient fill, smooth curve, trend badge
- **Stat Cards**: Large mono-font numbers with icon badges and trends
- **Appointments Table**: Avatar + name + date/time + status badges
- **Quick Actions**: Icon-labeled shortcuts to common tasks

🎯 **Brand Colors**
- Primary Blue: #4382DF
- Deep Navy: #112E81
- Secondary Indigo: #4647AE
- Soft Teal: #AACCD6
- Neutral Slate backgrounds

## Tech Stack

- **React** 18.3.1 with TypeScript
- **Tailwind CSS** for utility-first styling
- **Radix UI** for accessible components
- **Recharts** for data visualization
- **Lucide React** for icons
- **Vite** for fast dev server and build

## Project Structure

```
src/
├── components/
│   ├── dashboard/          # Reusable dashboard widgets
│   │   ├── trend-chart.tsx
│   │   ├── stat-card.tsx
│   │   ├── appointments-table.tsx
│   │   └── quick-actions.tsx
│   ├── layout/             # Layout containers
│   │   ├── sidebar.tsx
│   │   ├── header.tsx
│   │   └── dashboard-layout.tsx
│   └── ui/                 # Base UI primitives
│       ├── card.tsx
│       ├── badge.tsx
│       ├── avatar.tsx
│       ├── button.tsx
│       └── separator.tsx
├── data/
│   └── mock-data.ts        # Mock data for all 4 roles
├── lib/
│   ├── constants.ts        # Navigation items per role
│   └── utils.ts            # Helper functions (styling, formatting)
├── types/
│   └── index.ts            # TypeScript interfaces
├── App.tsx                 # Role switcher + main app
├── main.tsx                # React entry point
└── index.css               # Global styles & animations
```

## Getting Started

### Prerequisites
- Node.js 16+
- npm or yarn

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The app will open at `http://localhost:5173` (Vite default).

### Building

```bash
npm run build
```

### Preview

```bash
npm run preview
```

## Demo

The app includes a **role switcher** in the top-right corner for easy testing:
- Click `PATIENT`, `DOCTOR`, `SECRETARY`, or `ADMIN` to switch dashboards
- Each role has unique nav items, stats, and mock appointment data
- Sidebar and content update instantly

## Component Details

### TrendChart
Recharts AreaChart with:
- Gradient fill (`#4382DF` to transparent)
- Dashed horizontal grid lines
- Smooth monotone curve
- No data point dots
- Trend badge (up/down arrow + %)
- Responsive container

### StatCard
- Large mono-font number (tabular-nums)
- Uppercase label with tracking
- Icon badge (colored circle background)
- Optional hint text below divider
- Trend indicator
- Hover shadow effect

### AppointmentsTable
- Avatar with initials
- Patient name + doctor name
- Formatted date & time (tabular-nums)
- Status badge (color-coded)
- Scrollable on mobile
- "View All" button if 5+ appointments
- Empty state message

### QuickActions
- Icon badge (left)
- Title + description (left)
- Chevron icon (right)
- Row hover animation (slide-right)
- Semantic icons (lightning, clock, etc.)

### Sidebar
- Persistent on desktop, drawer on mobile
- Brand logo + wordmark
- Role badge (rounded-full)
- "MAIN" section label
- Nav items with active state indicator (left bar + dot)
- My Profile + Sign Out footer
- Keyboard accessible

### Header
- Page title (left)
- User avatar + name + role (right)
- Sticky, fixed at top
- Left margin on desktop (sidebar width)

## Mock Data

All data is static and defined in `src/data/mock-data.ts`:

- **USERS**: One per role with name, initials, email
- **Role Dashboards**: Config object per role with:
  - `title`: Page heading
  - `stats`: Array of StatCard data
  - `appointments`: Array of upcoming appointments
  - `trendData`: Array of trend values (dates + numbers)
  - `trendLabel` & `trendValue`: Chart header
  - `quickActions`: Array of action shortcuts

### Sample Stats
- Patient: Upcoming Appointments, Completed Appointments, Assigned Doctors, Medical Records
- Doctor: Today's Appointments, Upcoming Appointments, Active Patients, Rating
- Secretary: Pending Appointments, Walk-ins Today, Scheduled Today, Rescheduled
- Admin: Total Patients, Total Doctors, Total Appointments, Average Rating

## Styling & Animations

### Animations
- **fadeUp**: Cards fade in and slide up (0.5s ease-out)
- **slideRight**: Quick actions rows shift right on hover (0.3s ease-out)
- Staggered delays (~60-80ms per card) for cascade effect

### Colors
- Brand colors as CSS variables
- Tailwind `extends` for custom palette
- Status badges: blue (scheduled), indigo (rescheduled), teal (completed), red (cancelled)

### Responsive
- Mobile: 1-column grid, sheet drawer sidebar
- Tablet: 2-column grid
- Desktop: 4-column grid, fixed sidebar

## Accessibility

✅ **WCAG Compliant**
- Radix UI primitives (fully accessible)
- Visible focus rings (2px blue outline)
- Semantic HTML
- Button + link keyboard navigation
- ARIA attributes where needed
- Contrast ratios meet AA standard

## No Backend

This is a **frontend-only** dashboard:
- No API calls
- No state persistence
- No database integration
- Mock data only
- Role switching via local state

To integrate with a backend, replace mock data fetches with API calls in `App.tsx` or individual components.

## Customization

### Change Brand Colors
Edit `tailwind.config.js`:
```js
colors: {
  brand: {
    blue: "#YOUR_BLUE",
    navy: "#YOUR_NAVY",
    indigo: "#YOUR_INDIGO",
    teal: "#YOUR_TEAL",
  },
}
```

### Add/Remove Nav Items
Edit `src/lib/constants.ts` and `src/data/mock-data.ts`:
```ts
export const PATIENT_NAV = [
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  // Add more items...
];
```

### Adjust Grid Layout
In `src/components/layout/dashboard-layout.tsx`:
```tsx
<div className="grid ... md:grid-cols-2 lg:grid-cols-4">
  {/* Adjust col-span and cols per breakpoint */}
</div>
```

### Modify Mock Data
Edit `src/data/mock-data.ts` to update stats, appointments, and trends for each role.

## Browser Support

- Chrome/Edge (latest 2 versions)
- Firefox (latest 2 versions)
- Safari (latest 2 versions)
- Mobile browsers (iOS Safari, Chrome Android)

## License

MIT

## Notes

- This dashboard is production-ready for frontend demo purposes
- No authentication or API integration included
- All data is hardcoded for demonstration
- Icons are from lucide-react (100+ icons available)
- TypeScript strict mode enabled for type safety
