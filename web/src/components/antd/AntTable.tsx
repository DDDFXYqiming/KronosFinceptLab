"use client";

import { Table } from "antd";
import type { ColumnsType, TableProps } from "antd/es/table";

interface AntTableProps<T> {
  columns: ColumnsType<T>;
  dataSource: T[];
  rowKey?: TableProps<T>["rowKey"];
  loading?: boolean;
  scroll?: { x?: number; y?: number };
  className?: string;
  pagination?: false | { pageSize?: number; showSizeChanger?: boolean };
  locale?: { emptyText?: React.ReactNode };
}

export function AntTable<T extends object>({
  columns,
  dataSource,
  rowKey = "id",
  loading,
  scroll,
  className = "",
  pagination,
  locale,
}: AntTableProps<T>) {
  return (
    <Table<T>
      columns={columns}
      dataSource={dataSource}
      rowKey={rowKey}
      loading={loading}
      scroll={scroll}
      className={className}
      locale={locale}
      pagination={pagination === false ? false : { pageSize: pagination?.pageSize || 20, showSizeChanger: pagination?.showSizeChanger ?? true, ...(typeof pagination === 'object' ? pagination : {}) }}
      size="middle"
    />
  );
}
