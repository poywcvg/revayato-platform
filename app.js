/* ============================================
   CineSocial — App Logic & Mock Data
   ============================================ */

// --- Mock Data ---
const USERS = [
  { id: 1, name: 'Alex Morgan', username: '@alexmorgan', avatar: 'https://i.pravatar.cc/150?img=12', bio: 'Movie enthusiast & series binger. Love sci-fi and thrillers.', genres: ['Sci-Fi', 'Thriller', 'Drama'], followers: 234, following: 89, watched: 156, isCurrentUser: true },
  { id: 2, name: 'Ali Hassan', username: '@alihassan', avatar: 'https://i.pravatar.cc/150?img=1', bio: 'Cinema is life.', genres: ['Action', 'Sci-Fi'], followers: 189, following: 67, watched: 203 },
  { id: 3, name: 'Sara Kim', username: '@sarakim', avatar: 'https://i.pravatar.cc/150?img=5', bio: 'Documentary lover & foodie.', genres: ['Documentary', 'Comedy'], followers: 412, following: 145, watched: 312 },
  { id: 4, name: 'Nina Patel', username: '@ninapatel', avatar: 'https://i.pravatar.cc/150?img=8', bio: 'Horror queen. The scarier the better.', genres: ['Horror', 'Thriller'], followers: 156, following: 98, watched: 178 },
  { id: 5, name: 'Omar Farid', username: '@omarfarid', avatar: 'https://i.pravatar.cc/150?img=3', bio: 'Anime & series addict.', genres: ['Animation', 'Drama'], followers: 278, following: 134, watched: 267 },
  { id: 6, name: 'Lily Chen', username: '@lilychen', avatar: 'https://i.pravatar.cc/150?img=9', bio: 'Romance & indie films are my thing.', genres: ['Romance', 'Indie'], followers: 198, following: 76, watched: 145 },
  { id: 7, name: 'James Wright', username: '@jameswright', avatar: 'https://i.pravatar.cc/150?img=11', bio: 'Classic cinema enthusiast.', genres: ['Drama', 'Classic'], followers: 345, following: 112, watched: 489 },
];

const POSTERS = [
  'https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nez7.jpg',
  'https://image.tmdb.org/t/p/w500/qhb1qOilapbapxWQn9jtRCMwXJF.jpg',
  'https://image.tmdb.org/t/p/w500/q6y0Go1tsGEsmtFryDOJo3dEmqu.jpg',
  'https://image.tmdb.org/t/p/w500/3GHpljtnoBi8ICa4LrjC4B7Rl4R.jpg',
  'https://image.tmdb.org/t/p/w500/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg',
  'https://image.tmdb.org/t/p/w500/628Dep6AxEtDxjZoGP78TsOxYbK.jpg',
  'https://image.tmdb.org/t/p/w500/kuf6dutpsT0vzr3kTfFTfS45ag.jpg',
  'https://image.tmdb.org/t/p/w500/7WsyChQLEftFiDhRDUMsPfLbS0Z.jpg',
];

const HERO_MOVIES = [
  {
    title: 'Dune: Part Two',
    genres: ['Sci-Fi', 'Drama'],
    rating: 8.8,
    year: 2024,
    runtime: '2h 46m',
    lang: 'English',
    rated: 'PG-13',
    desc: 'Paul Atreides unites with Chani and the Fremen while on a warpath of revenge against the conspirators who destroyed his family.',
    bg: 'https://image.tmdb.org/t/p/original/xOMo8BRK7PfcJv9JCnx7s5hj0PX.jpg',
    friends: [1, 2, 5, 3],
  },
  {
    title: 'Oppenheimer',
    genres: ['Biography', 'Drama'],
    rating: 8.5,
    year: 2023,
    runtime: '3h 0m',
    lang: 'English',
    rated: 'R',
    desc: 'The story of American scientist J. Robert Oppenheimer and his role in the development of the atomic bomb.',
    bg: 'https://image.tmdb.org/t/p/original/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg',
    friends: [3, 4],
  },
  {
    title: 'The Last of Us',
    genres: ['Drama', 'Action'],
    rating: 8.8,
    year: 2023,
    runtime: 'Season 1',
    lang: 'English',
    rated: 'TV-MA',
    desc: 'Joel and Ellie navigate a post-apocalyptic America overrun by deadly infected and ruthless survivors.',
    bg: 'https://image.tmdb.org/t/p/original/uKvVjHNqB5VmOrdxqAt2F7J78ED.jpg',
    friends: [2, 5, 6],
  },
  {
    title: 'Inception',
    genres: ['Sci-Fi', 'Thriller'],
    rating: 8.8,
    year: 2010,
    runtime: '2h 28m',
    lang: 'English',
    rated: 'PG-13',
    desc: 'A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea.',
    bg: 'https://image.tmdb.org/t/p/original/9gk7adHYeDvHkCSEhniJIssEIaY.jpg',
    friends: [1, 7],
  },
  {
    title: 'Interstellar',
    genres: ['Sci-Fi', 'Drama'],
    rating: 8.6,
    year: 2014,
    runtime: '2h 49m',
    lang: 'English',
    rated: 'PG-13',
    desc: "A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
    bg: 'https://image.tmdb.org/t/p/original/xJHokMbljvjADYdit5fK0RXkCuo.jpg',
    friends: [4, 6],
  },
];

const MOVIES = [
  { id: 1, title: 'Dune: Part Two', year: 2024, rating: 8.8, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/8b8R8l88Qje9dn9OE8PY05Nez7.jpg', watched: false, progress: 0 },
  { id: 2, title: 'Oppenheimer', year: 2023, rating: 8.5, genre: 'Biography', poster: 'https://image.tmdb.org/t/p/w500/qhb1qOilapbapxWQn9jtRCMwXJF.jpg', watched: false, progress: 0 },
  { id: 3, title: 'The Last of Us', year: 2023, rating: 8.8, genre: 'Drama', poster: 'https://image.tmdb.org/t/p/w500/uKvVjHNqB5VmOrdxqAt2F7J78ED.jpg', watched: false, progress: 0 },
  { id: 4, title: 'Inception', year: 2010, rating: 8.8, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/9gk7adHYeDvHkCSEhniJIssEIaY.jpg', watched: true, progress: 0 },
  { id: 5, title: 'Interstellar', year: 2014, rating: 8.6, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/xJHokMbljvjADYdit5fK0RXkCuo.jpg', watched: false, progress: 0 },
  { id: 6, title: 'Breaking Bad', year: 2008, rating: 9.5, genre: 'Drama', poster: 'https://image.tmdb.org/t/p/w500/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg', watched: false, progress: 0 },
  { id: 7, title: 'The Dark Knight', year: 2008, rating: 9.0, genre: 'Action', poster: 'https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911BTUgMe1nF1iC.jpg', watched: true, progress: 0 },
  { id: 8, title: 'Parasite', year: 2019, rating: 8.6, genre: 'Thriller', poster: 'https://image.tmdb.org/t/p/w500/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg', watched: false, progress: 0 },
  { id: 9, title: 'Squid Game', year: 2021, rating: 8.0, genre: 'Thriller', poster: 'https://image.tmdb.org/t/p/w500/dDlEmu3EZ0Pgg93K2SVNLCjCSvE.jpg', watched: false, progress: 0 },
  { id: 10, title: 'Stranger Things', year: 2016, rating: 8.7, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/49WJfeN0moxb9IPfGn8AIqMGskD.jpg', watched: false, progress: 0 },
  { id: 11, title: 'Breaking Bad', year: 2008, rating: 9.5, genre: 'Crime', poster: 'https://image.tmdb.org/t/p/w500/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg', watched: false, progress: 0 },
  { id: 12, title: 'The Witcher', year: 2019, rating: 8.2, genre: 'Fantasy', poster: 'https://image.tmdb.org/t/p/w500/7vjaCdMw15FEbXyLQTVa04URsPm.jpg', watched: false, progress: 0 },
  { id: 13, title: 'Blade Runner 2049', year: 2017, rating: 8.0, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg', watched: false, progress: 0 },
  { id: 14, title: 'Arrival', year: 2016, rating: 7.9, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/x2FJsf1ElAgr83LEzPgA1T0EUsX.jpg', watched: false, progress: 0 },
  { id: 15, title: 'The Matrix', year: 1999, rating: 8.7, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg', watched: true, progress: 0 },
  { id: 16, title: 'Game of Thrones', year: 2011, rating: 9.3, genre: 'Fantasy', poster: 'https://image.tmdb.org/t/p/w500/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg', watched: false, progress: 0 },
  { id: 17, title: 'Tenet', year: 2020, rating: 7.3, genre: 'Action', poster: 'https://image.tmdb.org/t/p/w500/k62n8Qukjgx6RNK5wf7Jwb1CqkS.jpg', watched: false, progress: 0 },
  { id: 18, title: 'The Shining', year: 1980, rating: 8.4, genre: 'Horror', poster: 'https://image.tmdb.org/t/p/w500/nRj5511mZdTl4saWEPoj9QroTIu.jpg', watched: false, progress: 0 },
  { id: 19, title: 'Pulp Fiction', year: 1994, rating: 8.9, genre: 'Crime', poster: 'https://image.tmdb.org/t/p/w500/d5iIlFn5s0ImszYzBPb8JPIfbXD.jpg', watched: true, progress: 0 },
  { id: 20, title: 'The Godfather', year: 1972, rating: 9.2, genre: 'Crime', poster: 'https://image.tmdb.org/t/p/w500/3bhkrj58Vtu7enYsRolD1fZdja1.jpg', watched: false, progress: 0 },
  { id: 21, title: 'Moonlight', year: 2016, rating: 7.4, genre: 'Drama', poster: 'https://image.tmdb.org/t/p/w500/4911T5FbJ9eD2PvGX5D4N3TDNZS.jpg', watched: false, progress: 0 },
  { id: 22, title: 'Joker', year: 2019, rating: 8.2, genre: 'Drama', poster: 'https://image.tmdb.org/t/p/w500/udDclJoHjfjb8Ekgsd4FDteOkCU.jpg', watched: false, progress: 0 },
  { id: 23, title: 'Avengers: Endgame', year: 2019, rating: 8.4, genre: 'Action', poster: 'https://image.tmdb.org/t/p/w500/or06FN3Dka5tukK1e9sl16pB3iy.jpg', watched: false, progress: 0 },
  { id: 24, title: 'Dune', year: 2021, rating: 8.0, genre: 'Sci-Fi', poster: 'https://image.tmdb.org/t/p/w500/d5NXSklXo0qyIYkgV94XAgMIckC.jpg', watched: false, progress: 0 },
];

const CONTINUE_WATCHING = [
  { ...MOVIES[5], progress: 65 },
  { ...MOVIES[9], progress: 30 },
  { ...MOVIES[11], progress: 80 },
  { ...MOVIES[2], progress: 45 },
  { ...MOVIES[16], progress: 20 },
];

const ACTIVITIES = [
  { user: USERS[1], type: 'watched', movie: MOVIES[0], time: '2 hours ago' },
  { user: USERS[2], type: 'rated', movie: MOVIES[1], rating: 9, time: '3 hours ago', comment: 'Masterpiece of cinema!' },
  { user: USERS[3], type: 'watchlist', movie: MOVIES[7], time: '5 hours ago' },
  { user: USERS[4], type: 'watched', movie: MOVIES[2], time: '6 hours ago' },
  { user: USERS[5], type: 'rated', movie: MOVIES[4], rating: 10, time: '8 hours ago', comment: 'Changed my perspective on life.' },
  { user: USERS[1], type: 'shared', movie: MOVIES[12], time: '10 hours ago', comment: 'Visually stunning!' },
  { user: USERS[6], type: 'watched', movie: MOVIES[6], time: '12 hours ago' },
  { user: USERS[2], type: 'watchlist', movie: MOVIES[10], time: '1 day ago' },
];

const COLLECTIONS = [
  { name: 'Sci-Fi Essentials', count: 24, movies: [MOVIES[0], MOVIES[4], MOVIES[12], MOVIES[14]] },
  { name: 'Award Winners', count: 18, movies: [MOVIES[1], MOVIES[7], MOVIES[20], MOVIES[6]] },
  { name: 'Binge Worthy Series', count: 12, movies: [MOVIES[5], MOVIES[9], MOVIES[11], MOVIES[15]] },
  { name: 'Late Night Thrillers', count: 15, movies: [MOVIES[8], MOVIES[17], MOVIES[18], MOVIES[7]] },
];

const NOTIFICATIONS = [
  { user: USERS[1], text: '<strong>Ali</strong> started following you', time: '5m ago', unread: true },
  { user: USERS[2], text: '<strong>Sara</strong> rated Oppenheimer 9/10', time: '1h ago', unread: true },
  { user: USERS[3], text: '<strong>Nina</strong> added Dune to her watchlist', time: '2h ago', unread: true },
  { user: USERS[4], text: '<strong>Omar</strong> shared Interstellar with you', time: '4h ago', unread: false },
  { user: USERS[5], text: '<strong>Lily</strong> started watching The Last of Us', time: '6h ago', unread: false },
];

const WATCHLIST_MOVIES = [MOVIES[0], MOVIES[2], MOVIES[7], MOVIES[8], MOVIES[12], MOVIES[16], MOVIES[13], MOVIES[21]];

// --- State ---
let currentPage = 'home';
let currentHeroIndex = 0;
let savedItems = new Set([7, 15, 19]);
let followedUsers = new Set([2, 3, 5]);
let likedActivities = new Set();

// --- DOM Helpers ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function createEl(tag, className, innerHTML) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (innerHTML) el.innerHTML = innerHTML;
  return el;
}

function showToast(message, type = 'info') {
  const container = $('#toastContainer');
  const toast = createEl('div', `toast ${type}`, `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${type === 'success' ? '#00d68f' : '#3b82f6'}" stroke-width="2">
      ${type === 'success' 
        ? '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'
        : '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
      }
    </svg>
    ${message}
  `);
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// --- Render Functions ---

function renderMovieCard(movie, options = {}) {
  const { showProgress = false, progress = 0, showSocial = false, socialFriends = [], label = '' } = options;
  const isSaved = savedItems.has(movie.id);
  
  return `
    <div class="movie-card" data-movie-id="${movie.id}">
      <div class="movie-card-poster">
        <img src="${movie.poster}" alt="${movie.title}" loading="lazy" onerror="this.src='https://via.placeholder.com/180x270/1a1a26/ff3b3b?text=${encodeURIComponent(movie.title.substring(0,8))}'">
        <div class="movie-card-rating">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="#FFB800"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          ${movie.rating}
        </div>
        ${showSocial && socialFriends.length > 0 ? `
          <div class="movie-card-social">
            <div class="social-badge">
              <img src="${socialFriends[0].avatar}" alt="">
              +${socialFriends.length - 1}
            </div>
          </div>
        ` : ''}
        ${showProgress && progress > 0 ? `
          <div class="movie-card-progress">
            <div class="movie-card-progress-bar" style="width: ${progress}%"></div>
          </div>
        ` : ''}
        <div class="movie-card-overlay">
          <div class="movie-card-actions">
            <button class="card-action-btn play-btn-card" title="Watch" onclick="event.stopPropagation(); openPlayer('${movie.title.replace(/'/g, "\\'")}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </button>
            <button class="card-action-btn" title="Share" onclick="event.stopPropagation(); openShareModal('${movie.title.replace(/'/g, "\\'")}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            </button>
            <button class="card-action-btn save-btn ${isSaved ? 'saved' : ''}" title="Save" onclick="event.stopPropagation(); toggleSave(${movie.id}, this)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="${isSaved ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="movie-card-info">
        <h3>${movie.title}</h3>
        <div class="card-meta">
          <span>${movie.year}</span>
          <span class="dot"></span>
          <span>${movie.genre}</span>
        </div>
        ${label ? `
          <div class="movie-card-friends">
            <div class="mini-avatars">
              ${socialFriends.slice(0, 3).map(f => `<img src="${f.avatar}" alt="">`).join('')}
            </div>
            <span>${label}</span>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function renderActivityCard(activity) {
  const isLiked = likedActivities.has(activity.id || activity.time);
  const likeCount = Math.floor(Math.random() * 12) + 1;
  const commentCount = Math.floor(Math.random() * 5);

  let actionText = '';
  switch (activity.type) {
    case 'watched': actionText = 'watched'; break;
    case 'rated': actionText = `rated ${activity.rating}/10`; break;
    case 'watchlist': actionText = 'added to watchlist'; break;
    case 'shared': actionText = 'shared'; break;
  }

  return `
    <div class="activity-card">
      <div class="activity-card-header">
        <img class="activity-card-avatar" src="${activity.user.avatar}" alt="${activity.user.name}">
        <div class="activity-card-user">
          <div class="name">${activity.user.name}</div>
          <div class="action">${actionText}</div>
        </div>
        <div class="activity-card-time">${activity.time}</div>
      </div>
      <div class="activity-card-content">
        <img src="${activity.movie.poster}" alt="${activity.movie.title}">
        <div class="content-info">
          <h4>${activity.movie.title}</h4>
          <p>${activity.movie.year} · ${activity.movie.genre} · ${activity.movie.rating}</p>
          ${activity.comment ? `<p style="margin-top:6px;font-style:italic;color:var(--text-secondary)">"${activity.comment}"</p>` : ''}
        </div>
      </div>
      <div class="activity-card-interactions">
        <button class="interaction-btn ${isLiked ? 'liked' : ''}" onclick="toggleActivityLike('${activity.time}', this)">
          <svg viewBox="0 0 24 24" fill="${isLiked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
          <span>${isLiked ? likeCount + 1 : likeCount}</span>
        </button>
        <button class="interaction-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>${commentCount}</span>
        </button>
        <button class="interaction-btn" onclick="openShareModal('${activity.movie.title.replace(/'/g, "\\'")}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
          <span>Share</span>
        </button>
      </div>
    </div>
  `;
}

function renderFullActivityCard(activity) {
  let actionText = '';
  switch (activity.type) {
    case 'watched': actionText = 'watched'; break;
    case 'rated': actionText = `rated`; break;
    case 'watchlist': actionText = 'added to watchlist'; break;
    case 'shared': actionText = 'shared'; break;
  }

  return `
    <div class="social-feed-card">
      <div class="social-feed-header">
        <img class="social-feed-avatar" src="${activity.user.avatar}" alt="${activity.user.name}">
        <div class="social-feed-user-info">
          <div class="name">${activity.user.name}</div>
          <div class="action-text">${actionText} · ${activity.time}</div>
        </div>
        ${activity.type !== 'watchlist' ? `
          <button class="btn-follow ${followedUsers.has(activity.user.id) ? 'following' : ''}" onclick="toggleFollow(${activity.user.id}, this)">
            ${followedUsers.has(activity.user.id) ? 'Following' : 'Follow'}
          </button>
        ` : ''}
      </div>
      <div class="social-feed-body">
        <div class="social-feed-movie">
          <img src="${activity.movie.poster}" alt="${activity.movie.title}">
          <div class="movie-details">
            <h4>${activity.movie.title}</h4>
            <div class="meta">${activity.movie.year} · ${activity.movie.genre} · ${activity.movie.rating} <svg width="10" height="10" viewBox="0 0 24 24" fill="#FFB800" style="margin-left:2px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
            ${activity.rating ? `
              <div class="social-feed-rating">
                ${Array.from({length: 10}, (_, i) => `<span class="star" style="color:${i < activity.rating ? '#FFB800' : 'var(--text-tertiary)'}">★</span>`).join('')}
                <span class="score">${activity.rating}/10</span>
              </div>
            ` : ''}
            ${activity.comment ? `<p class="description">"${activity.comment}"</p>` : ''}
          </div>
        </div>
      </div>
      <div class="social-feed-footer">
        <button class="interaction-btn" onclick="toggleActivityLike('${activity.time}', this)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
          Like
        </button>
        <button class="interaction-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          Comment
        </button>
        <button class="interaction-btn" onclick="openShareModal('${activity.movie.title.replace(/'/g, "\\'")}')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
          Share
        </button>
      </div>
    </div>
  `;
}

function renderNotifications() {
  const list = $('#notifList');
  list.innerHTML = NOTIFICATIONS.map(n => `
    <div class="notif-item ${n.unread ? 'unread' : ''}">
      <img src="${n.user.avatar}" alt="${n.user.name}">
      <div class="notif-item-content">
        <p>${n.text}</p>
        <div class="notif-time">${n.time}</div>
      </div>
    </div>
  `).join('');
}

function renderProfile() {
  const user = USERS[0];
  const container = $('#profilePage');
  container.innerHTML = `
    <div class="profile-header">
      <img class="profile-avatar" src="${user.avatar}" alt="${user.name}">
      <div class="profile-info">
        <h1>${user.name}</h1>
        <div class="username">${user.username}</div>
        <p class="bio">${user.bio}</p>
        <div class="profile-genres">
          ${user.genres.map(g => `<span class="profile-genre-tag">${g}</span>`).join('')}
        </div>
        <div class="profile-stats">
          <div class="profile-stat">
            <div class="count">${user.followers}</div>
            <div class="label">Followers</div>
          </div>
          <div class="profile-stat">
            <div class="count">${user.following}</div>
            <div class="label">Following</div>
          </div>
          <div class="profile-stat">
            <div class="count">${user.watched}</div>
            <div class="label">Watched</div>
          </div>
        </div>
        <div class="profile-actions">
          <button class="btn btn-primary btn-sm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            Edit Profile
          </button>
          <button class="btn btn-outline btn-sm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
            Share Profile
          </button>
        </div>
      </div>
    </div>

    <div class="profile-tabs">
      <button class="profile-tab active" onclick="switchProfileTab('watched', this)">Watched</button>
      <button class="profile-tab" onclick="switchProfileTab('shared', this)">Shared</button>
      <button class="profile-tab" onclick="switchProfileTab('watchlist', this)">Watchlist</button>
      <button class="profile-tab" onclick="switchProfileTab('collections', this)">Collections</button>
    </div>

    <div class="profile-content" id="profileContent">
      <div class="profile-movies-grid">
        ${MOVIES.filter(m => m.watched).map(m => renderMovieCard(m)).join('')}
        ${MOVIES.slice(0, 6).map(m => renderMovieCard(m)).join('')}
      </div>
    </div>
  `;
}

function renderSettings() {
  const container = $('#settingsContent');
  container.innerHTML = `
    <div class="settings-group">
      <h3>Privacy & Social</h3>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Who can follow you</h4>
          <p>Control who is allowed to follow your profile</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Show watched history publicly</h4>
          <p>Allow others to see movies and series you've watched</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Allow comments on activity</h4>
          <p>Let friends comment on your shared watching activity</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Allow reactions on posts</h4>
          <p>Let friends like and react to your shared content</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Activity visible to followers only</h4>
          <p>Restrict your activity feed to only followers</p>
        </div>
        <label class="toggle">
          <input type="checkbox">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Show "Seen by friends" labels</h4>
          <p>Display which friends have watched content you're viewing</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>

    <div class="settings-group">
      <h3>Notifications</h3>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Push notifications</h4>
          <p>Get notified about new activity from friends</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Email notifications</h4>
          <p>Receive email digests of friend activity</p>
        </div>
        <label class="toggle">
          <input type="checkbox">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>New follower alerts</h4>
          <p>Get notified when someone follows you</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>

    <div class="settings-group">
      <h3>Playback</h3>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Auto-play next episode</h4>
          <p>Automatically play the next episode in a series</p>
        </div>
        <label class="toggle">
          <input type="checkbox" checked>
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Autoplay trailers</h4>
          <p>Play trailers when browsing content</p>
        </div>
        <label class="toggle">
          <input type="checkbox">
          <span class="toggle-slider"></span>
        </label>
      </div>
    </div>

    <div class="settings-group">
      <h3>Account</h3>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Email address</h4>
          <p>alex.morgan@email.com</p>
        </div>
        <button class="btn btn-outline btn-sm">Change</button>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Password</h4>
          <p>Last changed 3 months ago</p>
        </div>
        <button class="btn btn-outline btn-sm">Change</button>
      </div>
      <div class="settings-item">
        <div class="settings-item-left">
          <h4>Delete account</h4>
          <p>Permanently delete your account and data</p>
        </div>
        <button class="btn btn-outline btn-sm" style="border-color:var(--accent);color:var(--accent)">Delete</button>
      </div>
    </div>
  `;
}

function renderCollections() {
  const container = $('#collectionsGrid');
  container.innerHTML = COLLECTIONS.map(col => `
    <div class="collection-card">
      <div class="collection-card-mosaic">
        ${col.movies.slice(0, 3).map(m => `<img src="${m.poster}" alt="${m.title}" loading="lazy">`).join('')}
        <div style="background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--text-tertiary)">+${col.count - 3}</div>
      </div>
      <div class="collection-card-info">
        <h3>${col.name}</h3>
        <p>${col.count} titles</p>
      </div>
    </div>
  `).join('');
}

function renderHeroThumbnails() {
  const container = $('#heroThumbnails');
  container.innerHTML = HERO_MOVIES.map((m, i) => `
    <img class="hero-thumb ${i === currentHeroIndex ? 'active' : ''}" src="${m.bg}" alt="${m.title}" onclick="setHero(${i})">
  `).join('');
}

function setHero(index) {
  currentHeroIndex = index;
  const hero = HERO_MOVIES[index];
  
  $('#heroBg').style.backgroundImage = `url(${hero.bg})`;
  $('#heroTitle').textContent = hero.title;
  $('#heroDots').innerHTML = HERO_MOVIES.map((_, i) => 
    `<span class="dot ${i === index ? 'active' : ''}"></span>`
  ).join('');
  
  const tags = hero.genres.map(g => `<span class="tag tag-genre">${g}</span>`).join('');
  const isNew = index === 0;
  
  document.querySelector('.hero-tags').innerHTML = tags + (isNew ? '<span class="tag tag-new">New Season</span>' : '');
  document.querySelector('.hero-meta').innerHTML = `
    <span class="hero-rating"><svg width="14" height="14" viewBox="0 0 24 24" fill="#FFB800" stroke="#FFB800" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> ${hero.rating}</span>
    <span class="dot-sep">·</span>
    <span>${hero.year}</span>
    <span class="dot-sep">·</span>
    <span>${hero.runtime}</span>
    <span class="dot-sep">·</span>
    <span>${hero.lang}</span>
    <span class="dot-sep">·</span>
    <span>${hero.rated}</span>
  `;
  document.querySelector('.hero-desc').textContent = hero.desc;
  
  const friendAvatars = hero.friends.map(uid => {
    const user = USERS.find(u => u.id === uid);
    return user ? `<img src="${user.avatar}" alt="" class="friend-avatar-stack">` : '';
  }).join('');
  const friendNames = hero.friends.map(uid => USERS.find(u => u.id === uid)?.name).filter(Boolean);
  const friendsText = friendNames.length > 2 
    ? `${friendNames[0]}, ${friendNames[1]} and ${friendNames.length - 2} friends watched this`
    : `${friendNames.join(', ')} watched this`;
  
  document.querySelector('.friend-avatars').innerHTML = friendAvatars;
  document.querySelector('.hero-friends-text').textContent = friendsText;
  
  renderHeroThumbnails();
}

function renderHomeContent() {
  // Continue Watching
  $('#continueWatching').innerHTML = CONTINUE_WATCHING.map(m => 
    renderMovieCard(m, { showProgress: true, progress: m.progress })
  ).join('');

  // Trending Now
  const trendingFriends = [USERS[1], USERS[2], USERS[5]];
  $('#trendingNow').innerHTML = MOVIES.slice(0, 8).map((m, i) => 
    renderMovieCard(m, { 
      showSocial: i < 3, 
      socialFriends: i < 3 ? trendingFriends.slice(0, Math.min(3, trendingFriends.length)) : [] 
    })
  ).join('');

  // Friends Activity
  $('#friendsActivity').innerHTML = ACTIVITIES.map(a => renderActivityCard(a)).join('');

  // Recommended
  $('#recommended').innerHTML = MOVIES.slice(8, 16).map(m => renderMovieCard(m)).join('');

  // Friends Watched
  const friendsWatchedData = [
    { movie: MOVIES[0], friends: [USERS[1], USERS[2]], label: 'Ali and Sara watched' },
    { movie: MOVIES[3], friends: [USERS[4], USERS[6]], label: 'Omar and James liked' },
    { movie: MOVIES[4], friends: [USERS[5]], label: 'Shared by Lily' },
    { movie: MOVIES[6], friends: [USERS[1], USERS[3], USERS[4]], label: '3 friends watched' },
    { movie: MOVIES[1], friends: [USERS[2]], label: 'Recommended by Sara' },
    { movie: MOVIES[7], friends: [USERS[6], USERS[5]], label: 'Seen by people you follow' },
  ];
  $('#friendsWatched').innerHTML = friendsWatchedData.map(d => 
    renderMovieCard(d.movie, { showSocial: true, socialFriends: d.friends, label: d.label })
  ).join('');

  // Popular This Week
  $('#popularWeek').innerHTML = [...MOVIES].sort(() => Math.random() - 0.5).slice(0, 8).map(m => renderMovieCard(m)).join('');
}

function renderExplorePage() {
  $('#exploreGrid').innerHTML = MOVIES.map(m => renderMovieCard(m)).join('');
}

function renderTrendingPage() {
  const container = $('#trendingList');
  container.innerHTML = MOVIES.slice(0, 10).map((m, i) => {
    const change = Math.random() > 0.3;
    const changeAmount = Math.floor(Math.random() * 5) + 1;
    const randomFriends = [USERS[1], USERS[3], USERS[5]].slice(0, Math.floor(Math.random() * 3) + 1);
    return `
      <div class="trending-item" onclick="openPlayer('${m.title.replace(/'/g, "\\'")}')">
        <div class="trending-rank">${i + 1}</div>
        <img src="${m.poster}" alt="${m.title}" loading="lazy">
        <div class="trending-info">
          <h3>${m.title}</h3>
          <div class="meta">${m.year} · ${m.genre} · ${m.rating} <svg width="10" height="10" viewBox="0 0 24 24" fill="#FFB800" style="margin-left:2px"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></div>
        </div>
        <div class="trending-social">
          <div class="mini-avatars">
            ${randomFriends.map(f => `<img src="${f.avatar}" alt="">`).join('')}
          </div>
          <span>${randomFriends.length} friends</span>
        </div>
        <div class="trending-change ${change ? 'up' : 'down'}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            ${change ? '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>' : '<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/>'}
          </svg>
          ${changeAmount}
        </div>
      </div>
    `;
  }).join('');
}

function renderFollowingPage() {
  const container = $('#followingFeed');
  container.innerHTML = ACTIVITIES.map(a => renderFullActivityCard(a)).join('');
}

function renderWatchlistPage() {
  const container = $('#watchlistGrid');
  container.innerHTML = WATCHLIST_MOVIES.map(m => renderMovieCard(m)).join('');
}

// --- Interactions ---

function navigateTo(page) {
  currentPage = page;
  
  $$('.page').forEach(p => p.classList.remove('active'));
  const targetPage = $(`#page-${page}`);
  if (targetPage) targetPage.classList.add('active');
  
  $$('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.page === page);
  });
  
  switch (page) {
    case 'home': renderHomeContent(); setHero(currentHeroIndex); break;
    case 'explore': renderExplorePage(); break;
    case 'trending': renderTrendingPage(); break;
    case 'following': renderFollowingPage(); break;
    case 'watchlist': renderWatchlistPage(); break;
    case 'collections': renderCollections(); break;
    case 'profile': renderProfile(); break;
    case 'settings': renderSettings(); break;
  }
  
  // Close mobile sidebar
  $('#sidebar').classList.remove('open');
  
  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleSave(movieId, btn) {
  if (savedItems.has(movieId)) {
    savedItems.delete(movieId);
    btn.classList.remove('saved');
    btn.querySelector('svg').setAttribute('fill', 'none');
    showToast('Removed from watchlist', 'info');
  } else {
    savedItems.add(movieId);
    btn.classList.add('saved');
    btn.querySelector('svg').setAttribute('fill', 'currentColor');
    showToast('Added to watchlist', 'success');
  }
}

function toggleFollow(userId, btn) {
  if (followedUsers.has(userId)) {
    followedUsers.delete(userId);
    btn.textContent = 'Follow';
    btn.classList.remove('following');
    showToast('Unfollowed', 'info');
  } else {
    followedUsers.add(userId);
    btn.textContent = 'Following';
    btn.classList.add('following');
    showToast('Now following!', 'success');
  }
}

function toggleActivityLike(activityTime, btn) {
  if (likedActivities.has(activityTime)) {
    likedActivities.delete(activityTime);
    btn.classList.remove('liked');
    const svg = btn.querySelector('svg');
    svg.setAttribute('fill', 'none');
    const countSpan = btn.querySelector('span');
    if (countSpan) countSpan.textContent = parseInt(countSpan.textContent) - 1;
  } else {
    likedActivities.add(activityTime);
    btn.classList.add('liked');
    const svg = btn.querySelector('svg');
    svg.setAttribute('fill', 'currentColor');
    const countSpan = btn.querySelector('span');
    if (countSpan) countSpan.textContent = parseInt(countSpan.textContent) + 1;
  }
}

function openShareModal(title) {
  const modal = $('#shareModal');
  const body = $('#shareModalBody');
  body.innerHTML = `
    <p style="margin-bottom:16px;color:var(--text-secondary);font-size:14px">Share "${title}" with friends</p>
    <div class="share-options">
      <div class="share-option" onclick="showToast('Link copied!', 'success')">
        <div class="share-option-icon" style="background:var(--accent-gradient)">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
        </div>
        <span>Copy Link</span>
      </div>
      <div class="share-option">
        <div class="share-option-icon" style="background:#25D366">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
        </div>
        <span>WhatsApp</span>
      </div>
      <div class="share-option">
        <div class="share-option-icon" style="background:#1DA1F2">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg>
        </div>
        <span>Twitter</span>
      </div>
      <div class="share-option">
        <div class="share-option-icon" style="background:linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>
        </div>
        <span>Instagram</span>
      </div>
    </div>
    <div class="share-link">
      <input type="text" value="https://cinesocial.app/title/${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}" readonly>
      <button class="btn btn-primary btn-sm" onclick="showToast('Link copied!', 'success')">Copy</button>
    </div>
  `;
  modal.classList.add('open');
}

function openPlayer(title) {
  const modal = $('#playerModal');
  $('#playerTitle').textContent = title;
  modal.classList.add('open');
}

function closeModals() {
  $$('.modal-overlay').forEach(m => m.classList.remove('open'));
}

function switchProfileTab(tab, btn) {
  $$('.profile-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  
  const content = $('#profileContent');
  switch (tab) {
    case 'watched':
      content.innerHTML = `<div class="profile-movies-grid">${MOVIES.filter(m => m.watched).map(m => renderMovieCard(m)).join('')}${MOVIES.slice(0, 6).map(m => renderMovieCard(m)).join('')}</div>`;
      break;
    case 'shared':
      content.innerHTML = ACTIVITIES.filter(a => a.user.id === 1).map(a => renderFullActivityCard(a)).join('');
      if (!content.innerHTML) content.innerHTML = '<p style="color:var(--text-secondary);padding:40px;text-align:center">No shared activity yet.</p>';
      break;
    case 'watchlist':
      content.innerHTML = `<div class="profile-movies-grid">${WATCHLIST_MOVIES.map(m => renderMovieCard(m)).join('')}</div>`;
      break;
    case 'collections':
      content.innerHTML = `<div class="collections-grid">${COLLECTIONS.map(col => `
        <div class="collection-card">
          <div class="collection-card-mosaic">
            ${col.movies.slice(0, 3).map(m => `<img src="${m.poster}" alt="${m.title}">`).join('')}
            <div style="background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:var(--text-tertiary)">+${col.count - 3}</div>
          </div>
          <div class="collection-card-info">
            <h3>${col.name}</h3>
            <p>${col.count} titles</p>
          </div>
        </div>
      `).join('')}</div>`;
      break;
  }
}

// --- Event Listeners ---
document.addEventListener('DOMContentLoaded', () => {
  // Nav items
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(item.dataset.page);
    });
  });

  // User menu items
  $$('.user-menu-item[data-page]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(item.dataset.page);
      $('#userMenu').classList.remove('open');
    });
  });

  // Hero navigation
  $('#heroPrev').addEventListener('click', () => {
    setHero((currentHeroIndex - 1 + HERO_MOVIES.length) % HERO_MOVIES.length);
  });
  $('#heroNext').addEventListener('click', () => {
    setHero((currentHeroIndex + 1) % HERO_MOVIES.length);
  });

  // Notifications
  $('#notifBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    $('#notifPanel').classList.toggle('open');
    $('#userMenu').classList.remove('open');
  });

  // User menu
  $('#userAvatarBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    $('#userMenu').classList.toggle('open');
    $('#notifPanel').classList.remove('open');
  });

  // Close menus on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#notifPanel') && !e.target.closest('#notifBtn')) {
      $('#notifPanel').classList.remove('open');
    }
    if (!e.target.closest('#userMenu') && !e.target.closest('#userAvatarBtn')) {
      $('#userMenu').classList.remove('open');
    }
  });

  // Modal close buttons
  $('#closeShareModal').addEventListener('click', closeModals);
  $('#closePlayer').addEventListener('click', closeModals);
  $$('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModals();
    });
  });

  // Mobile menu
  $('#mobileMenuBtn').addEventListener('click', () => {
    $('#sidebar').classList.toggle('open');
  });

  // Keyboard shortcut: Cmd/Ctrl + K for search
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      $('#globalSearch').focus();
    }
    if (e.key === 'Escape') {
      closeModals();
      $('#notifPanel').classList.remove('open');
      $('#userMenu').classList.remove('open');
    }
  });

  // Filter chips
  $$('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      $$('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    });
  });

  // Tab buttons
  $$('.tab-btn').forEach(tab => {
    tab.addEventListener('click', () => {
      tab.parentElement.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
    });
  });

  // Hero watchlist button
  $('#heroWatchlistBtn').addEventListener('click', function() {
    showToast('Added to watchlist!', 'success');
    this.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
      In Watchlist
    `;
    this.style.borderColor = 'var(--accent)';
    this.style.color = 'var(--accent)';
  });

  // Auto-rotate hero
  let heroInterval = setInterval(() => {
    setHero((currentHeroIndex + 1) % HERO_MOVIES.length);
  }, 8000);

  // Pause auto-rotate on hover
  $('#heroBanner').addEventListener('mouseenter', () => clearInterval(heroInterval));
  $('#heroBanner').addEventListener('mouseleave', () => {
    heroInterval = setInterval(() => {
      setHero((currentHeroIndex + 1) % HERO_MOVIES.length);
    }, 8000);
  });

  // --- Initial Render ---
  renderHomeContent();
  setHero(0);
  renderNotifications();
  renderHeroThumbnails();
});
