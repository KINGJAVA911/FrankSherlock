import { useCallback, useMemo, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  cancelScan, copyFilesToClipboard, deleteFiles, ensureDatabase,
  getCliFolderPath, getFileMetadata, listRoots,
  removeRoot, renameFile, reorderRoots, startScan, updateFileMetadata,
} from "./api";
import type {
  DbStats,
  DuplicateGroup,
  FileMetadata,
  RootInfo,
  RuntimeStatus,
  SearchItem,
  SetupStatus,
  SortField,
  SortOrder,
} from "./types";
import { errorMessage } from "./utils";
import { fileName } from "./utils/format";
import Titlebar from "./components/Titlebar/Titlebar";
import Sidebar from "./components/Sidebar/Sidebar";
import Content from "./components/Content/Content";
import DuplicatesView from "./components/Content/DuplicatesView";
import FacesView from "./components/Content/FacesView";
import PdfPasswordsView from "./components/Content/PdfPasswordsView";
import ContextMenu from "./components/Content/ContextMenu";
import StatusBar from "./components/StatusBar/StatusBar";
import ToastContainer from "./components/Toasts/ToastContainer";
import SetupModal from "./components/modals/SetupModal";
import ResumeModal from "./components/modals/ResumeModal";
import ScanSummaryModal from "./components/modals/ScanSummaryModal";
import PreviewModal from "./components/modals/PreviewModal";
import ConfirmDeleteModal from "./components/modals/ConfirmDeleteModal";
import ConfirmFileDeleteModal from "./components/modals/ConfirmFileDeleteModal";
import RenameModal from "./components/modals/RenameModal";
import HelpModal from "./components/modals/HelpModal";
import EditMetadataModal from "./components/modals/EditMetadataModal";
import PropertiesModal from "./components/modals/PropertiesModal";
import ModelInfoModal from "./components/modals/ModelInfoModal";
import CreateAlbumModal from "./components/modals/CreateAlbumModal";
import CreateSmartFolderModal from "./components/modals/CreateSmartFolderModal";
import { useToast } from "./hooks/useToast";
import { useUserConfig } from "./hooks/useUserConfig";
import { useGridColumns } from "./hooks/useGridColumns";
import { useInfiniteScroll } from "./hooks/useInfiniteScroll";
import { usePolling } from "./hooks/usePolling";
import { useSelection } from "./hooks/useSelection";
import { useSearch } from "./hooks/useSearch";
import { useScanManager } from "./hooks/useScanManager";
import { useGridNavigation } from "./hooks/useGridNavigation";
import { useAppInit } from "./hooks/useAppInit";
import { useAutoUpdate } from "./hooks/useAutoUpdate";
import { useFaceDetection } from "./hooks/useFaceDetection";
import { useAlbumManager } from "./hooks/useAlbumManager";
import { useSmartFolderManager } from "./hooks/useSmartFolderManager";
import { useDuplicatesManager } from "./hooks/useDuplicatesManager";
import "./app.css";

const POLL_MS = 1200;

export default function App() {
  /* ── Core UI state ── */
  const [query, setQuery] = useState("");
  const [selectedMediaType, setSelectedMediaType] = useState("");
  const [sortBy, setSortBy] = useState<SortField>("dateModified");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [dbStats, setDbStats] = useState<DbStats | null>(null);
  const [roots, setRoots] = useState<RootInfo[]>([]);
  const [selectedRootId, setSelectedRootId] = useState<number | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [showResumeModal, setShowResumeModal] = useState(false);
  const [confirmDeleteRoot, setConfirmDeleteRoot] = useState<RootInfo | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [contextMenuMeta, setContextMenuMeta] = useState<{ description: string; extractedText: string } | null>(null);
  const [confirmDeleteFiles, setConfirmDeleteFiles] = useState<SearchItem[] | null>(null);
  const [renameItem, setRenameItem] = useState<SearchItem | null>(null);
  const [showModelInfo, setShowModelInfo] = useState(false);
  const [editMetadataItem, setEditMetadataItem] = useState<SearchItem | null>(null);
  const [propertiesItem, setPropertiesItem] = useState<SearchItem | null>(null);
  const [forceShowSetup, setForceShowSetup] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [pdfPasswordsMode, setPdfPasswordsMode] = useState(false);

  /* ── Directory tree: derived from query ── */
  const selectedSubdir = useMemo(() => {
    const match = query.match(/\bsubdir:(?:"([^"]+)"|(\S+))/i);
    return match ? (match[1] ?? match[2] ?? null) : null;
  }, [query]);

  /* ── Refs ── */
  const sentinelRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  /* ── Toast ── */
  const { notice, error, setNotice, setError } = useToast();
  useUserConfig();
  const columnsRef = useGridColumns(gridRef);

  /* ── Feature hooks ── */
  const autoUpdate = useAutoUpdate({ onNotice: setNotice, onError: setError });
  const faces = useFaceDetection({ pollMs: POLL_MS, onNotice: setNotice, onError: setError });
  const albumManager = useAlbumManager({ onNotice: setNotice, onError: setError });
  const smartFolderManager = useSmartFolderManager({ onNotice: setNotice, onError: setError });
  const duplicates = useDuplicatesManager({ onNotice: setNotice, onError: setError });

  /* ── Selection ── */
  const {
    selectedIndices, focusIndex, anchorIndex,
    selectOnly, toggleSelect, rangeSelect, selectAll, clearSelection, replaceSelection,
  } = useSelection();

  const onReconcileSelection = useCallback((oldItems: SearchItem[], newItems: SearchItem[]) => {
    if (selectedIndices.size === 0) return;
    const selectedIds = new Set<number>();
    let focusId: number | null = null;
    let anchorId: number | null = null;
    for (const idx of selectedIndices) {
      if (idx < oldItems.length) {
        selectedIds.add(oldItems[idx].id);
      }
    }
    if (focusIndex !== null && focusIndex < oldItems.length) {
      focusId = oldItems[focusIndex].id;
    }
    if (anchorIndex !== null && anchorIndex < oldItems.length) {
      anchorId = oldItems[anchorIndex].id;
    }
    const newSelection = new Set<number>();
    let newFocus: number | null = null;
    let newAnchor: number | null = null;
    for (let i = 0; i < newItems.length; i++) {
      const id = newItems[i].id;
      if (selectedIds.has(id)) newSelection.add(i);
      if (id === focusId) newFocus = i;
      if (id === anchorId) newAnchor = i;
    }
    replaceSelection(newSelection, newFocus, newAnchor);
  }, [selectedIndices, focusIndex, anchorIndex, replaceSelection]);

  /* ── Search ── */
  const {
    items, total, loading, loadingMore, canLoadMore, runSearch, onLoadMore,
  } = useSearch({
    query,
    selectedMediaType,
    selectedRootId,
    sortBy,
    sortOrder,
    isReady: !setup || setup.isReady,
    onClearSelection: clearSelection,
    onReconcileSelection,
  });

  /* ── Scan manager ── */
  const scanManager = useScanManager({
    setSetup,
    setRuntime,
    setDbStats,
    setRoots,
    setReadOnly,
    setShowResumeModal,
    setNotice,
    setError,
    runSearch,
    itemsLength: () => items.length,
  });

  /* ── Init app: also load albums + smart folders + CLI folder ── */
  const initApp = useCallback(async () => {
    const result = await scanManager.initApp();
    await albumManager.refreshAlbums();
    await smartFolderManager.refreshSmartFolders();

    if (!result) return;
    const cliPath = await getCliFolderPath();
    if (!cliPath) return;

    const { roots: loadedRoots, scans, setupStatus, readOnly: isReadOnly } = result;
    const matchingRoot = loadedRoots.find((r) => r.rootPath === cliPath);
    const activeOrInterrupted = scans.filter(
      (s) => s.status === "running" || s.status === "interrupted",
    );

    if (matchingRoot) {
      setSelectedRootId(matchingRoot.id);
      const interruptedForRoot = activeOrInterrupted.find(
        (s) => s.rootPath === cliPath && s.status === "interrupted",
      );
      if (interruptedForRoot && !isReadOnly && setupStatus.isReady) {
        try {
          const job = await startScan(cliPath);
          scanManager.addTrackedJobId(job.id);
        } catch { /* ignore */ }
      }
    } else if (!isReadOnly && setupStatus.isReady) {
      const hasRunning = activeOrInterrupted.some((s) => s.status === "running");
      if (hasRunning) return;
      try {
        const job = await startScan(cliPath);
        scanManager.addTrackedJobId(job.id);
        await scanManager.refreshRoots();
        const updatedRoots = await listRoots();
        const newRoot = updatedRoots.find((r) => r.rootPath === cliPath);
        if (newRoot) setSelectedRootId(newRoot.id);
      } catch { /* ignore */ }
    }
  }, [scanManager.initApp]);

  useAppInit(initApp);
  usePolling(POLL_MS, scanManager.pollRuntimeAndScans, [scanManager.trackedJobIds]);
  useInfiniteScroll(sentinelRef, onLoadMore, [items.length, total, loadingMore]);

  const hasModalOpen = !!(confirmDeleteFiles || renameItem || editMetadataItem || propertiesItem || albumManager.showCreateAlbum || smartFolderManager.showCreateSmartFolder);

  const onRequestDelete = useCallback(() => {
    const filesToDelete = [...selectedIndices].sort((a, b) => a - b)
      .filter(i => i < items.length)
      .map(i => items[i]);
    if (filesToDelete.length > 0) setConfirmDeleteFiles(filesToDelete);
  }, [selectedIndices, items]);

  const onRequestRename = useCallback(() => {
    if (selectedIndices.size !== 1) return;
    const idx = [...selectedIndices][0];
    if (idx < items.length) setRenameItem(items[idx]);
  }, [selectedIndices, items]);

  useGridNavigation({
    items,
    selectedIndices,
    focusIndex,
    anchorIndex,
    columnsRef,
    gridRef,
    previewOpen,
    showSummary: scanManager.trackedJobIds.length === 0 && scanManager.completedJobs.length > 0,
    showResumeModal,
    confirmDeleteRoot,
    setup,
    canLoadMore,
    hasModalOpen,
    selectOnly,
    rangeSelect,
    selectAll,
    clearSelection,
    setPreviewOpen,
    setCompletedJobs: scanManager.setCompletedJobs,
    setShowResumeModal,
    setConfirmDeleteRoot,
    setNotice,
    onLoadMore,
    showHelp,
    setShowHelp,
    onRequestDelete,
    onRequestRename,
    forceShowSetup,
    setForceShowSetup,
  });

  /* ── Derived values ── */
  const mediaTypeOptions = useMemo(
    () => ["", "document", "anime", "screenshot", "photo", "artwork", "manga", "other"],
    []
  );

  const isScanning = scanManager.activeScans.some((s) => s.status === "running");
  const runningScansCount = scanManager.activeScans.filter((s) => s.status === "running").length;
  const interruptedScans = scanManager.activeScans.filter((s) => s.status === "interrupted");
  const showSummary = scanManager.trackedJobIds.length === 0 && scanManager.completedJobs.length > 0;

  const previewItems: SearchItem[] = previewOpen
    ? [...selectedIndices].sort((a, b) => a - b).slice(0, 10).filter(i => i < items.length).map(i => items[i])
    : [];
  const singlePreviewIndex = selectedIndices.size === 1 ? [...selectedIndices][0] : null;

  const activeAlbumName = useMemo(() => {
    const match = query.match(/^album:(?:"([^"]+)"|(\S+))$/i);
    return match ? (match[1] ?? match[2] ?? null) : null;
  }, [query]);

  const subtitle = useMemo(() => {
    if (faces.facesMode) return "Faces";
    if (pdfPasswordsMode) return "PDF Passwords";
    if (duplicates.duplicatesMode) return "Find Duplicates";
    if (activeAlbumName) return activeAlbumName;
    const sf = smartFolderManager.smartFolders.find(f => f.id === smartFolderManager.activeSmartFolderId);
    if (sf) return sf.name;
    if (selectedRootId != null) {
      const root = roots.find(r => r.id === selectedRootId);
      if (root) {
        return selectedSubdir ? `${root.rootName} / ${selectedSubdir}` : root.rootName;
      }
    }
    return null;
  }, [faces.facesMode, duplicates.duplicatesMode, activeAlbumName, smartFolderManager.activeSmartFolderId, smartFolderManager.smartFolders, selectedRootId, roots, selectedSubdir, pdfPasswordsMode]);

  /* ── Mode switching coordination ── */
  function enterDuplicatesMode(threshold?: number | null) {
    setPdfPasswordsMode(false);
    faces.setFacesMode(false);
    duplicates.onFindDuplicates(threshold);
  }

  function enterFacesMode() {
    faces.setFacesMode(true);
    duplicates.setDuplicatesMode(false);
    setPdfPasswordsMode(false);
  }

  function enterPdfPasswordsMode() {
    setPdfPasswordsMode(true);
    duplicates.setDuplicatesMode(false);
    faces.setFacesMode(false);
  }

  /* ── Handlers ── */
  function onWindowClose() {
    void getCurrentWindow().close();
  }

  async function onDeleteRoot(root: RootInfo) {
    if (readOnly) return;
    setConfirmDeleteRoot(null);
    try {
      const runningForRoot = scanManager.activeScans.filter(
        (s) => s.rootId === root.id && s.status === "running",
      );
      for (const scan of runningForRoot) {
        await cancelScan(scan.id);
      }
      if (runningForRoot.length > 0) {
        await new Promise((r) => setTimeout(r, 300));
      }
      const result = await removeRoot(root.id);
      if (selectedRootId === root.id) setSelectedRootId(null);
      setNotice(`Removed "${root.rootName}": ${result.filesRemoved} files purged.`);
      await scanManager.refreshRoots();
      const stats = await ensureDatabase();
      setDbStats(stats);
      await runSearch(0, false);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function onTileClick(idx: number, e: React.MouseEvent) {
    if (e.ctrlKey || e.metaKey) {
      toggleSelect(idx);
    } else if (e.shiftKey && anchorIndex != null) {
      rangeSelect(anchorIndex, idx);
    } else {
      selectOnly(idx);
    }
  }

  function onTileDoubleClick(idx: number) {
    selectOnly(idx);
    setPreviewOpen(true);
  }

  function onTileContextMenu(idx: number, e: React.MouseEvent) {
    e.preventDefault();
    if (!selectedIndices.has(idx)) selectOnly(idx);
    setContextMenu({ x: e.clientX, y: e.clientY });

    const effectiveSelection = selectedIndices.has(idx) ? selectedIndices : new Set([idx]);
    if (effectiveSelection.size === 1) {
      const item = items[idx];
      if (item) {
        getFileMetadata(item.id)
          .then((meta) => setContextMenuMeta({ description: meta.description, extractedText: meta.extractedText }))
          .catch(() => setContextMenuMeta(null));
      }
    } else {
      setContextMenuMeta(null);
    }
  }

  function handleContextCopyPath() {
    setContextMenu(null);
    const paths = [...selectedIndices].sort((a, b) => a - b)
      .filter(i => i < items.length)
      .map(i => items[i].absPath);
    if (paths.length > 0) {
      copyFilesToClipboard(paths).catch(() => {});
      setNotice(`Copied ${paths.length} file path(s)`);
    }
  }

  function handleContextCopyDescription() {
    setContextMenu(null);
    if (!contextMenuMeta?.description) return;
    copyFilesToClipboard([contextMenuMeta.description]).catch(() => {});
    setNotice("Copied description");
  }

  function handleContextCopyOcrText() {
    setContextMenu(null);
    if (!contextMenuMeta?.extractedText) return;
    copyFilesToClipboard([contextMenuMeta.extractedText]).catch(() => {});
    setNotice("Copied OCR text");
  }

  function handleContextRename() {
    setContextMenu(null);
    onRequestRename();
  }

  function handleContextDelete() {
    setContextMenu(null);
    onRequestDelete();
  }

  function handleContextEditMetadata() {
    setContextMenu(null);
    if (selectedIndices.size !== 1) return;
    const idx = [...selectedIndices][0];
    if (idx >= items.length) return;
    const item = items[idx];
    if (item.confidence === 0) {
      setNotice("This file hasn't been classified yet");
      return;
    }
    setEditMetadataItem(item);
  }

  function handleContextProperties() {
    setContextMenu(null);
    if (selectedIndices.size !== 1) return;
    const idx = [...selectedIndices][0];
    if (idx < items.length) setPropertiesItem(items[idx]);
  }

  async function handleDeleteFiles() {
    if (!confirmDeleteFiles) return;
    const ids = confirmDeleteFiles.map(f => f.id);
    setConfirmDeleteFiles(null);
    try {
      const result = await deleteFiles(ids);
      clearSelection();
      await runSearch(0, false);
      const stats = await ensureDatabase();
      setDbStats(stats);
      setNotice(`Deleted ${result.deletedCount} file(s)`);
      if (result.errors.length > 0) {
        setError(`Some files had errors: ${result.errors[0]}`);
      }
      if (duplicates.duplicatesMode) {
        await duplicates.refreshAfterDelete();
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleRenameFile(newName: string) {
    if (!renameItem) return;
    const item = renameItem;
    setRenameItem(null);
    try {
      await renameFile(item.id, newName);
      clearSelection();
      await runSearch(0, false);
      setNotice(`Renamed to "${newName}"`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleSaveMetadata(data: FileMetadata) {
    setEditMetadataItem(null);
    try {
      await updateFileMetadata(
        data.id,
        data.mediaType,
        data.description,
        data.extractedText,
        data.canonicalMentions,
        data.locationText,
      );
      await runSearch(0, false);
      setNotice("Metadata updated");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  /* ── Album handler wrappers (coordinate mode switching) ── */
  function handleSelectAlbum(album: typeof albumManager.albums[number]) {
    const { query: q } = albumManager.onSelectAlbum(album);
    setQuery(q);
    smartFolderManager.setActiveSmartFolderId(null);
    duplicates.setDuplicatesMode(false);
    setPdfPasswordsMode(false);
    faces.setFacesMode(false);
  }

  function handleAddToAlbum(albumId: number) {
    setContextMenu(null);
    const fileIds = [...selectedIndices].sort((a, b) => a - b)
      .filter(i => i < items.length)
      .map(i => items[i].id);
    albumManager.onAddToAlbum(albumId, fileIds);
  }

  function handleCreateAlbumFromSelection() {
    setContextMenu(null);
    const fileIds = [...selectedIndices].sort((a, b) => a - b)
      .filter(i => i < items.length)
      .map(i => items[i].id);
    albumManager.onCreateAlbumFromSelection(fileIds);
  }

  /* ── Smart folder handler wrappers (coordinate mode switching) ── */
  function handleSelectSmartFolder(folder: typeof smartFolderManager.smartFolders[number]) {
    const { query: q } = smartFolderManager.onSelectSmartFolder(folder);
    setQuery(q);
    duplicates.setDuplicatesMode(false);
    setPdfPasswordsMode(false);
    faces.setFacesMode(false);
  }

  function handleCreateSmartFolderConfirm(name: string) {
    smartFolderManager.onCreateSmartFolderConfirm(name, query);
  }

  /* ── Duplicates handler wrappers ── */
  function handleDuplicatesDeleteSelected() {
    const filesToDelete = duplicates.getDeleteSearchItems();
    if (filesToDelete.length > 0) setConfirmDeleteFiles(filesToDelete);
  }

  function handleDuplicatesPreviewGroup(group: DuplicateGroup) {
    setConfirmDeleteFiles(null);
    setPreviewOpen(false);
    duplicates.onPreviewGroup(group);
  }

  /* ── Reorder handlers ── */
  async function handleReorderRoots(ids: number[]) {
    try {
      await reorderRoots(ids);
      await scanManager.refreshRoots();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  /* ── JSX ── */
  return (
    <div className="app-shell">
      {/* ── Modals ── */}
      {setup && (!setup.isReady || forceShowSetup) && (
        <SetupModal setup={setup} onRecheck={scanManager.onRecheckSetup} onDownload={scanManager.onSetupDownload} onSetupOcr={scanManager.onSetupOcr} onClose={forceShowSetup ? () => setForceShowSetup(false) : undefined} />
      )}
      {showResumeModal && (
        <ResumeModal
          interruptedScans={interruptedScans}
          onDismiss={() => setShowResumeModal(false)}
          onResumeAll={scanManager.onResumeAllInterrupted}
        />
      )}
      {showSummary && (
        <ScanSummaryModal completedJobs={scanManager.completedJobs} onClose={() => scanManager.setCompletedJobs([])} />
      )}
      {previewItems.length > 0 && (
        <PreviewModal
          previewItems={previewItems}
          selectedCount={selectedIndices.size}
          singlePreviewIndex={singlePreviewIndex}
          totalItems={items.length}
          onClose={() => setPreviewOpen(false)}
          onNavigate={(idx) => { selectOnly(idx); }}
        />
      )}
      {duplicates.dupPreviewItems.length > 0 && (
        <PreviewModal
          previewItems={duplicates.dupPreviewItems}
          selectedCount={duplicates.dupPreviewItems.length}
          singlePreviewIndex={null}
          totalItems={duplicates.dupPreviewItems.length}
          onClose={() => duplicates.setDupPreviewItems([])}
          onNavigate={() => {}}
        />
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      {showModelInfo && runtime && (
        <ModelInfoModal runtime={runtime} setup={setup} onClose={() => setShowModelInfo(false)} />
      )}
      {confirmDeleteRoot && (
        <ConfirmDeleteModal
          root={confirmDeleteRoot}
          isScanning={scanManager.activeScans.some(
            (s) => s.rootId === confirmDeleteRoot.id && s.status === "running",
          )}
          onCancel={() => setConfirmDeleteRoot(null)}
          onConfirm={onDeleteRoot}
        />
      )}
      {confirmDeleteFiles && (
        <ConfirmFileDeleteModal
          files={confirmDeleteFiles}
          onCancel={() => setConfirmDeleteFiles(null)}
          onConfirm={handleDeleteFiles}
        />
      )}
      {renameItem && (
        <RenameModal
          currentName={fileName(renameItem.relPath)}
          onCancel={() => setRenameItem(null)}
          onConfirm={handleRenameFile}
        />
      )}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          selectedCount={selectedIndices.size}
          albums={albumManager.albums}
          description={contextMenuMeta?.description ?? null}
          extractedText={contextMenuMeta?.extractedText ?? null}
          confidence={selectedIndices.size === 1 ? (items[[...selectedIndices][0]]?.confidence ?? null) : null}
          onCopyPath={handleContextCopyPath}
          onCopyDescription={handleContextCopyDescription}
          onCopyOcrText={handleContextCopyOcrText}
          onRename={handleContextRename}
          onEditMetadata={handleContextEditMetadata}
          onProperties={handleContextProperties}
          onDelete={handleContextDelete}
          onAddToAlbum={handleAddToAlbum}
          onCreateAlbumFromSelection={handleCreateAlbumFromSelection}
          onClose={() => setContextMenu(null)}
        />
      )}
      {editMetadataItem && (
        <EditMetadataModal
          fileId={editMetadataItem.id}
          onSave={handleSaveMetadata}
          onCancel={() => setEditMetadataItem(null)}
        />
      )}
      {propertiesItem && (
        <PropertiesModal
          fileId={propertiesItem.id}
          onClose={() => setPropertiesItem(null)}
        />
      )}
      {albumManager.showCreateAlbum && (
        <CreateAlbumModal
          onCancel={albumManager.closeCreateModal}
          onConfirm={albumManager.onCreateAlbumConfirm}
        />
      )}
      {smartFolderManager.showCreateSmartFolder && (
        <CreateSmartFolderModal
          query={query}
          onCancel={smartFolderManager.closeCreateModal}
          onConfirm={handleCreateSmartFolderConfirm}
        />
      )}

      {/* ── Titlebar ── */}
      <Titlebar
        onClose={onWindowClose}
        subtitle={subtitle}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed(c => !c)}
      />

      {/* ── Read-Only Banner ── */}
      {readOnly && (
        <div className="readonly-banner">
          Read-only mode — database cannot be modified
        </div>
      )}

      {/* ── Main Area ── */}
      <div className={`main-area${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
        <Sidebar
          roots={roots}
          selectedRootId={selectedRootId}
          activeScans={scanManager.activeScans}
          dbStats={dbStats}
          readOnly={readOnly}
          setupReady={setup ? setup.isReady : false}
          albums={albumManager.albums}
          smartFolders={smartFolderManager.smartFolders}
          activeAlbumName={activeAlbumName}
          activeSmartFolderId={smartFolderManager.activeSmartFolderId}
          selectedSubdir={selectedSubdir}
          onSelectSubdir={(subdir) => {
            setQuery((q) => {
              const cleaned = q.replace(/\bsubdir:(?:"[^"]*?"|\S+)\s*/i, "").trim();
              if (!subdir) return cleaned;
              const prefix = subdir.includes(" ") ? `subdir:"${subdir}"` : `subdir:${subdir}`;
              return cleaned ? `${prefix} ${cleaned}` : prefix;
            });
            smartFolderManager.setActiveSmartFolderId(null);
          }}
          onSelectRoot={(id) => {
            setSelectedRootId(id);
            setQuery((q) => q.replace(/\bsubdir:(?:"[^"]*?"|\S+)\s*/i, "").trim());
            duplicates.setDuplicatesMode(false);
            setPdfPasswordsMode(false);
            faces.setFacesMode(false);
          }}
          onDeleteRoot={(root) => setConfirmDeleteRoot(root)}
          onRescanRoot={(root) => scanManager.onRescanRoot(root, setup, readOnly)}
          onRefreshRoot={(root) => scanManager.onRefreshRoot(root, readOnly)}
          onCopyRootPath={(root) => {
            copyFilesToClipboard([root.rootPath]).catch(() => {});
            setNotice(`Copied path: ${root.rootPath}`);
          }}
          onPickAndScan={() => scanManager.onPickAndScan(setup, readOnly)}
          onCancelScan={(scan) => scanManager.onCancelScan(scan, readOnly)}
          onResumeScan={(scan) => scanManager.onResumeScan(scan, readOnly)}
          onSelectAlbum={handleSelectAlbum}
          onDeleteAlbum={albumManager.onDeleteAlbum}
          onSelectSmartFolder={handleSelectSmartFolder}
          onDeleteSmartFolder={smartFolderManager.onDeleteSmartFolder}
          onReorderRoots={handleReorderRoots}
          onReorderAlbums={albumManager.onReorderAlbums}
          onReorderSmartFolders={smartFolderManager.onReorderSmartFolders}
          faceProgress={faces.faceProgress}
          onDetectFaces={faces.onDetectFaces}
          onCancelFaceDetect={faces.onCancelFaceDetect}
          onFindDuplicates={enterDuplicatesMode}
          onOpenPdfPasswords={enterPdfPasswordsMode}
          onOpenFaces={enterFacesMode}
          updateInfo={autoUpdate.updateInfo}
          updateChecking={autoUpdate.updateChecking}
          updateDownloading={autoUpdate.updateDownloading}
          updateProgress={autoUpdate.updateProgress}
          onCheckUpdates={() => autoUpdate.checkForUpdates(false)}
          onInstallUpdate={autoUpdate.installUpdate}
        />

        {faces.facesMode ? (
          <FacesView
            onBack={() => faces.setFacesMode(false)}
            onPreview={(item) => {
              clearSelection();
              const idx = items.findIndex((i) => i.id === item.id);
              if (idx >= 0) {
                selectOnly(idx);
                setPreviewOpen(true);
              } else {
                duplicates.setDupPreviewItems([item]);
              }
            }}
          />
        ) : pdfPasswordsMode ? (
          <PdfPasswordsView
            onBack={() => setPdfPasswordsMode(false)}
            onNotice={setNotice}
            onError={setError}
          />
        ) : duplicates.duplicatesMode && duplicates.duplicatesData ? (
          <DuplicatesView
            data={duplicates.duplicatesData}
            loading={duplicates.duplicatesLoading}
            selected={duplicates.duplicatesSelected}
            nearEnabled={duplicates.nearEnabled}
            nearThreshold={duplicates.nearThreshold}
            onNearEnabledChange={duplicates.onNearEnabledChange}
            onNearThresholdChange={duplicates.onNearThresholdChange}
            onToggleFile={duplicates.onToggleFile}
            onSelectAllDuplicates={duplicates.onSelectAllDuplicates}
            onDeselectAll={duplicates.onDeselectAll}
            onDeleteSelected={handleDuplicatesDeleteSelected}
            onBack={duplicates.onBack}
            onSelectGroupDuplicates={duplicates.onSelectGroupDuplicates}
            onPreviewGroup={handleDuplicatesPreviewGroup}
          />
        ) : (
          <Content
            query={query}
            onQueryChange={(q) => { setQuery(q); smartFolderManager.setActiveSmartFolderId(null); }}
            selectedMediaType={selectedMediaType}
            onMediaTypeChange={setSelectedMediaType}
            mediaTypeOptions={mediaTypeOptions}
            sortBy={sortBy}
            onSortByChange={setSortBy}
            sortOrder={sortOrder}
            onSortOrderChange={setSortOrder}
            hasTextQuery={query.trim().length > 0}
            onSaveSmartFolder={smartFolderManager.openCreateModal}
            items={items}
            total={total}
            loading={loading}
            loadingMore={loadingMore}
            canLoadMore={canLoadMore}
            isScanning={isScanning}
            selectedRootName={selectedRootId != null ? (roots.find((r) => r.id === selectedRootId)?.rootName ?? null) : null}
            selectedIndices={selectedIndices}
            focusIndex={focusIndex}
            gridRef={gridRef}
            sentinelRef={sentinelRef}
            onTileClick={onTileClick}
            onTileDoubleClick={onTileDoubleClick}
            onTileContextMenu={onTileContextMenu}
          />
        )}
      </div>

      {/* ── Status Bar ── */}
      <StatusBar
        runtime={runtime}
        isScanning={isScanning}
        runningScansCount={runningScansCount}
        selectedCount={selectedIndices.size}
        onShowModelInfo={() => setShowModelInfo(true)}
      />

      {/* ── Toasts ── */}
      <ToastContainer notice={notice} error={error} />
    </div>
  );
}
