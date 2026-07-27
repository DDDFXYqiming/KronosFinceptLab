"use client";

import { Table } from "antd";
import { ColumnsType } from "antd/es/table";

interface AntTableProps<T> {
  columns: ColumnsType<T>;
  dataSource: T[];
  rowKey?: string | ((record: T) => string);
  loading?: boolean;
  scroll?: { x?: number; y?: number };
  className?: string;
  pagination?: false | { pageSize?: number; showSizeChanger?: boolean };
}

export function AntTable<T extends object>({
  columns,
  dataSource,
  rowKey = "id",
  loading,
  scroll,
  className = "",
  pagination,
}: AntTableProps<T>) {
  return (
    <Table<T>
      columns={columns}
      dataSource={dataSource}
      rowKey={rowKey}
      loading={loading}
      scroll={scroll}
      className={className}
      pagination={pagination === false ? false : { pageSize: pagination?.pageSize || 20, showSizeChanger: pagination?.showSizeChanger ?? true, ...(typeof pagination === 'object' ? pagination : {}) }}
      size="middle"
    />
  );
}
